import os
from PIL import Image, ImageDraw

def create_hobby_object(filename: str, color: str, text: str):
    # Create a 200x200 transparent image
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw a circle
    margin = 10
    draw.ellipse([margin, margin, 200-margin, 200-margin], fill=color, outline="white", width=4)
    
    # Add text to make it obvious
    draw.text((60, 90), text, fill="white")
    
    img.save(filename)
    print(f"Created hobby object: {filename}")

if __name__ == "__main__":
    os.makedirs("template_test/objects", exist_ok=True)
    create_hobby_object("template_test/objects/football.png", "brown", "FOOTBALL")
    create_hobby_object("template_test/objects/toy_car.png", "red", "TOY CAR")
    create_hobby_object("template_test/objects/apple.png", "darkred", "APPLE")
    create_hobby_object("template_test/objects/book.png", "blue", "BOOK")
    create_hobby_object("template_test/objects/teddy_bear.png", "peru", "TEDDY")
