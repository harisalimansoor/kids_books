import sys
import argparse
import cv2
import torch
import time
import os
from pathlib import Path

GHOST_ROOT = Path(__file__).resolve().parent
if str(GHOST_ROOT) not in sys.path:
    sys.path.insert(0, str(GHOST_ROOT))


def ghost_path(*parts):
    return str(GHOST_ROOT.joinpath(*parts))

# This repo calls .cuda() throughout inference. On a CPU-only machine those
# calls have to stay on the host device, and fp16 kernels are CUDA-only.
if not torch.cuda.is_available():
    def _cpu_tensor(self, *args, **kwargs):
        return self

    def _cpu_module(self, *args, **kwargs):
        return self

    torch.Tensor.cuda = _cpu_tensor
    torch.nn.Module.cuda = _cpu_module
    torch.cuda.empty_cache = lambda: None


def _load_weights(path):
    try:
        return torch.load(path, map_location=torch.device('cpu'), weights_only=False)
    except TypeError:
        return torch.load(path, map_location=torch.device('cpu'))


from utils.inference.image_processing import crop_face, get_final_image
from utils.inference.video_processing import get_target, face_enhancement
from utils.inference.core import model_inference

from network.AEI_Net import AEI_Net
from coordinate_reg.image_infer import Handler
from insightface_func.face_detect_crop_multi import Face_detect_crop
from arcface_model.iresnet import iresnet100
from models.pix2pix_model import Pix2PixModel
from models.config_sr import TestOptions


def init_models(args):
    ctx_id = 0 if torch.cuda.is_available() else -1
    # model for face cropping
    app = Face_detect_crop(name='antelope', root=ghost_path('insightface_func', 'models'))
    app.prepare(ctx_id=ctx_id, det_thresh=0.6, det_size=(640,640))

    # main model for generation
    G = AEI_Net(args.backbone, num_blocks=args.num_blocks, c_id=512)
    G.eval()
    G.load_state_dict(_load_weights(args.G_path))
    G = G.cuda()
    if torch.cuda.is_available():
        G = G.half()

    # arcface model to get face embedding
    netArc = iresnet100(fp16=False)
    netArc.load_state_dict(_load_weights(ghost_path('arcface_model', 'backbone.pth')))
    netArc=netArc.cuda()
    netArc.eval()

    # model to get face landmarks 
    handler = Handler(ghost_path('coordinate_reg', 'model', '2d106det'), 0, ctx_id=ctx_id, det_size=640, root=ghost_path('insightface_func', 'models'))

    # model to make superres of face, set use_sr=True if you want to use super resolution or use_sr=False if you don't
    if args.use_sr:
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'
        torch.backends.cudnn.benchmark = True
        opt = TestOptions()
        #opt.which_epoch ='10_7'
        model = Pix2PixModel(opt)
        model.netG.train()
    else:
        model = None
    
    return app, G, netArc, handler, model
    
    
def main(args):
    app, G, netArc, handler, model = init_models(args)
    
    # get crops from source images
    print('List of source paths: ',args.source_paths)
    source = []
    try:
        for source_path in args.source_paths: 
            img = cv2.imread(source_path)
            img = crop_face(img, app, args.crop_size)[0]
            source.append(img[:, :, ::-1])
    except TypeError:
        print("Bad source images!")
        exit()
        
    target_full = cv2.imread(args.target_image)
    if target_full is None:
        print(f"Could not read target image: {args.target_image}")
        raise SystemExit(1)
    full_frames = [target_full]
    
    # get target faces that are used for swap
    set_target = True
    print('List of target paths: ', args.target_faces_paths)
    if not args.target_faces_paths:
        target = get_target(full_frames, app, args.crop_size)
        set_target = False
    else:
        target = []
        for target_faces_path in args.target_faces_paths:
            img = cv2.imread(target_faces_path)
            if img is None:
                print(f"Bad target images! Could not read {target_faces_path}")
                raise SystemExit(1)
            try:
                img = crop_face(img, app, args.crop_size)[0]
            except TypeError:
                # Already a tight face crop, so keep it instead of detecting again.
                img = cv2.resize(img, (args.crop_size, args.crop_size))
            target.append(img)
        
    start = time.time()
    final_frames_list, crop_frames_list, full_frames, tfm_array_list = model_inference(full_frames,
                                                                                       source,
                                                                                       target,
                                                                                       netArc,
                                                                                       G,
                                                                                       app, 
                                                                                       set_target,
                                                                                       similarity_th=args.similarity_th,
                                                                                       crop_size=args.crop_size,
                                                                                       BS=args.batch_size,
                                                                                       half=torch.cuda.is_available())
    if args.use_sr:
        final_frames_list = face_enhancement(final_frames_list, model)

    result = get_final_image(final_frames_list, crop_frames_list, full_frames[0], tfm_array_list, handler)
    cv2.imwrite(args.out_image_name, result)
    print(f'Swapped Image saved with path {args.out_image_name}')
    print('Total time: ', time.time()-start)
    

def build_parser():
    parser = argparse.ArgumentParser()

    # Generator params
    parser.add_argument('--G_path', default=ghost_path('weights', 'G_unet_2blocks.pth'), type=str, help='Path to weights for G')
    parser.add_argument('--backbone', default='unet', const='unet', nargs='?', choices=['unet', 'linknet', 'resnet'], help='Backbone for attribute encoder')
    parser.add_argument('--num_blocks', default=2, type=int, help='Numbers of AddBlocks at AddResblock')

    parser.add_argument('--batch_size', default=40, type=int)
    parser.add_argument('--crop_size', default=224, type=int, help="Don't change this")
    parser.add_argument('--use_sr', default=False, type=bool, help='True for super resolution on swap images')
    parser.add_argument('--similarity_th', default=0.15, type=float, help='Threshold for selecting a face similar to the target')

    parser.add_argument('--source_paths', default=['examples/images/mark.jpg'], nargs='+')
    parser.add_argument('--target_faces_paths', default=[], nargs='+', help='Reference faces in the target image. Skip this to swap onto the detected face.')

    parser.add_argument('--target_image', default='examples/images/beckham.jpg', type=str, help='Image that receives the swapped face')
    parser.add_argument('--out_image_name', default='examples/results/result.png', type=str,help="It's necessary for image to image swap")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    main(args)