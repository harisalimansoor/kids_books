# What this folder is and how we run it

Read this before changing anything. It describes the face-swap test we are running now, and how that sits next to the workbook app.

## One-sentence picture

`ghost/` is a local copy of the GHOST face-swap model. We run it by hand on a question template plus user face photos. It is not called by the workbook, the API, or the React frontend. Google Drive is the later plan. Right now every image is local, because this is the testing phase.

GHOST replaces a face only. Hair, clothes, body, hands, background, and objects stay exactly as they are in the template. Do not draw, inpaint, or edit the result after the model writes it. The test is the model's own output.

## Where this sits in the repo

Repo root (parent of this folder):

`D:\Office Data Muneeb\myintelibooks-512046776fa99b9c1489236ff208fbe556f655f0`

| Path | What it is | Does it call GHOST? |
| --- | --- | --- |
| `run.py` | Starts the workbook app (FastAPI backend + React frontend, or the old Streamlit UI). | No |
| `frontend/` | React + Vite UI. Sibling of `ghost/`, not inside it. | No |
| `app/newapp.py` | Streamlit workbook screen. User enters name, grade, topics, and can upload family photos. | No |
| `app/stem_pipeline.py` | Picks ready question templates, fills `{user_name}` and family names, builds MCQ options. | No |
| `app/pdf_generator.py` | Writes the PDF. | No |
| `app/image_generator.py` | Old prompt-based image generator. Not the path used now. | No |
| `ghost/` | This folder. Face swap only. | This is the model |

Current workbook behaviour, from the code:

- `app/newapp.py` sets `use_ai_generate = False`.
- `app/stem_pipeline.py` `build_workbook_items()` deletes `face_paths` and sets every question `image_path` to `None`.
- The PDF gets question text and options. It does not get a swapped picture.
- `ghost/__init__.py` says the same thing: added inside MyInteliBooks, not connected to workbook generation yet.

## Testing strategy

Later: a Google Drive folder per question. Read the related template from that folder. Write the swapped image back into that same folder.

Now: the same idea, on disk. Drive is not connected. No Drive client, no credentials, no upload step.

Intended local shape of one question folder:

```text
clusters/<question>/
  template.jpg     related scene image
  roles.json       who is left-to-right
  swapped.png      GHOST output, same folder
```

User face photos do not live in that folder. They are separate inputs (a child photo, a grandfather photo, and so on).

The code does not yet save `swapped.png` beside the template. `swap_by_question.py` still writes the default output to `examples/results/<folder name>.png` unless `--out` is passed. Test images that were produced during this session have been deleted.

## How one swap actually runs

Command, from this folder, using the already-installed GHOST virtualenv (CPU PyTorch; the system Python does not have torch):

```text
C:\Users\Ishq E Ali\Downloads\ghost-main\.venv\Scripts\python.exe swap_by_question.py --question "child and grandfather" --clusters clusters --input child=inputs/q1/child.jpg --input grandfather=inputs/q1/grandfather.jpg --out examples/results/q1_shapes.png --batch_size 1
```

Steps inside `swap_by_question.py`:

1. Turn the question text into role names. `"child and grandfather"` becomes `child`, `grandfather`.
2. Find a subfolder of `--clusters` whose `roles.json` has the same set of roles.
3. Read `roles_left_to_right`. That list is the order of faces in the template from left to right. It must match the question's roles.
4. Load `template.jpg` (or the file named in `roles.json` / `--template`).
5. Detect every face and sort them by horizontal center. Face count must equal the role count.
6. Pair role 1 with the leftmost face, role 2 with the next face, and so on.
7. Crop each template face and call `inference.main`.
8. `inference.py` loads the GHOST generator, ArcFace, the face detector, and the landmark model, swaps each source photo onto the matching template face, and pastes the new face back onto the original template.
9. Write the PNG to `--out`.

Important bug already hit: if two cluster folders have the same roles, `find_cluster()` returns the first folder name in alphabetical order. `--template` only picks a file inside the chosen folder. It does not pick the folder. Pointing both "shapes" and "apples" at `child` + `grandfather` made the apples run use the shapes template. To force one template, call the inference path with that template path directly, or keep only one matching cluster.

A second manual path was used when only one face should change (the woman on the right, then the boy on the left). That path detects faces, keeps only the chosen landmark, and passes a single source plus a single target crop into `inference.main`. The other face is never sent to the model.

## What was tested, then deleted

These runs completed. The image files were deleted afterwards. `roles.json` files are still on disk. The image files are not.

| Run | Template | Sources | Who was swapped | Output that existed |
| --- | --- | --- | --- | --- |
| Question 1, Finding Shapes with Grandpa | boy left, grandfather right, 3 shape cards | child photo + grandfather photo | both faces | `examples/results/q1_shapes.png` |
| Question 2, Sharing Apples | girl left, grandfather right, 6 apples on 2 plates | girl photo + a different grandfather photo | both faces | `examples/results/q2_apples.png` |
| Classroom, first | boy left, woman right | one woman photo | right face only | `examples/results/mom_swap.png` |
| Classroom, second | the previous output | a second woman photo | right face only, onto the previous output | `examples/results/mom_swap_2.png` |
| Classroom, third | the previous output | one boy/young-man photo | left face only | `examples/results/mom_swap_3.png` |

Question text those templates belonged to (not stored as code, only used as the test brief):

- Finding Shapes with Grandpa: 1 circle, 1 triangle, 1 square. Which shape has 3 straight sides?
- Sharing Apples with Grandfather: 6 apples shared equally on 2 plates. How many on each plate?
- Erasing Stars with Grandpa was described but not run. The stars template was never swapped.
- The classroom image (boy, woman, whiteboard `6√754`) was a separate face-swap check, not one of those three questions.

## Files in this folder, one by one

### Files we run

`swap_by_question.py`
The test entry point. Maps a question to a cluster folder, orders faces left to right, and calls inference. This is the script to extend when the local folder (and later Drive) should read a template and write `swapped.png` back into that same folder.

`inference.py`
Loads models and runs one image-to-image swap. `source_paths` are the user photos. `target_faces_paths` are cropped faces from the template, in the same order. `target_image` is the full scene the faces are pasted onto. `out_image_name` is the PNG path. On a machine with no CUDA it replaces `.cuda()` with a no-op so the same code stays on CPU, and it turns half precision off. Weights default to `weights/G_unet_2blocks.pth`. Crop size stays 224.

`__init__.py`
Marks this folder as the GHOST package inside MyInteliBooks and states that workbook generation is not connected.

`requirements.txt`
Python packages the model needs: torch, opencv, insightface 0.2.1, mxnet 1.7.0.post2, onnxruntime, kornia 0.6.12, and the rest. The working interpreter is the `.venv` under `C:\Users\Ishq E Ali\Downloads\ghost-main`, not a venv inside this repo.

`clusters/finding_shapes/roles.json`
`clusters/sharing_apples/roles.json`
Both say `{"roles_left_to_right": ["child", "grandfather"]}`. Their `template.jpg` files were deleted. These two folders are the local stand-in for the future Drive question folders.

### Model code (do not treat this as app logic)

`network/AEI_Net.py`, `network/AADLayer.py`, `network/resnet.py`, `network/MultiscaleDiscriminator.py`
The GHOST generator. `AEI_Net` is what `inference.py` loads.

`arcface_model/iresnet.py` and `arcface_model/backbone.pth`
Identity embedding. Used to match a source face to the right face in the template. The `.pth` is a weight file and is gitignored.

`insightface_func/face_detect_crop_multi.py` and `face_detect_crop_single.py`
Face detector wrapper. Model file: `insightface_func/models/antelope/scrfd_10g_bnkps.onnx` (gitignored).

`coordinate_reg/image_infer.py` and `coordinate_reg/model/2d106det*`
106-point landmarks used when the swapped face is pasted back. The `.params` weight is gitignored. The symbol JSON can stay in git.

`utils/inference/core.py`
Batch loop: embed the target crops, find those faces again on the full image, embed each source, run the generator.

`utils/inference/faceshifter_run.py`
One generator forward pass.

`utils/inference/image_processing.py`
Crop a face, normalise tensors, and `get_final_image()`, which warps the swapped crop back onto the template with a face mask.

`utils/inference/masks.py`
The static face mask used at paste time. This is why hair outside the mask stays from the template.

`utils/inference/video_processing.py`
Face match by embedding similarity, plus the frame helpers the image path also uses. `similarity_th` defaults to 0.15.

`utils/inference/util.py`
Small helpers.

`models/pix2pix_model.py`, `models/config_sr.py`, `models/networks/`
Optional super-resolution. Inference only builds it when `--use_sr` is true. We have been running with super-resolution off.

`weights/G_unet_2blocks.pth`
Generator checkpoint. Present on disk, too large to commit. Parent `.gitignore` ignores `ghost/weights/*.pth`, `ghost/arcface_model/*.pth`, the onnx detector, the landmark `.params`, and `ghost/examples/results/`.

`LICENSE`
Upstream GHOST licence.

### Folders that were only for the test

`inputs/q1/`, `inputs/q2/`, `inputs/mom_swap/`
User photos used as swap sources. The photos were deleted. The directories may still be empty.

`examples/results/`
Where the PNG outputs were written. Those PNGs were deleted.

## Rules for the next change

- Keep testing local until Drive is explicitly requested.
- One question, one folder. Template in, swapped result back into that same folder.
- Do not post-edit the PNG. The point of the test is GHOST's own result.
- Do not wire this into `app/stem_pipeline.py` or the React app until that integration is requested.
- Do not commit the weight files or the generated result images.
- If two questions share the same roles, select the folder by path. Do not rely on `find_cluster()` while both folders are present.
