"""Test all four fraction question types."""
from blueprint_generator import generate_blueprint

questions = [
    # Type 1: Half circled (with role)
    'Look at the picture! {grandmother_name} has 4 books in front of her. Half of them are circled. How many books are circled?',
    'Look at the picture! {father_name} has 8 books in front of him. Half of them are circled. How many books are circled?',
    'Look at the picture! {sibling_name} has 6 stickers in front of her. Half of them are circled. How many stickers are circled?',

    # Type 2: Equal groups (no role)
    'Look at the picture! There are 8 pennies divided into 4 equal groups. One group is circled. How many pennies are in the circled group?',
    'Look at the picture! There are 12 cookies on the table, divided into 4 equal groups. One group is circled. How many cookies are in the circled group?',
    'Look at the picture! There are 4 cookies divided into 4 equal groups. One group is circled. How many cookies are in the circled group?',

    # Type 3: Each divided into parts
    'Look at the picture! There are 3 circles, each divided into 5 parts. How many parts are there altogether?',
    'Look at the picture! There are 3 oranges, each cut into 2 halves. How many orange halves are there altogether?',

    # Type 4: Clock
    'Look at the picture! There is a clock showing 1 hour. The hand has moved three-quarters of the way around. How many minutes have passed?',
]

for q in questions:
    img, meta = generate_blueprint(q)
    objs = [(g['object'], g['count']) for g in meta['objects']]
    fi = meta.get('fraction_info')
    ft = fi['fraction_type'] if fi else 'none'
    ans = fi.get('answer', '?') if fi else '?'
    n_chars = len(meta['characters'])
    print('---')
    print(f'Q: {q[:60]}...')
    print(f'  type={ft}, answer={ans}, chars={n_chars}, objs={objs}')
    img.save(f'blueprint_{ft}.png' if ft != 'none' else 'blueprint_test.png')
