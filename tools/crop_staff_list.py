import os
from PIL import Image

scale_to_px = 128


def handle_crop():
    """A messy script to load in all the images in uncropped, resize them to scale_to_px (and scale_to_px*2 for @2x) and centre crop them to be square!
    Expects staff names in image like `this is ignored - Melissa Autumn.jpg` -> `melissa-autumn.png"""
    for root, dirs, files in os.walk('../media/img/thunderbird/staff/uncropped'):
        for file in files:
            with Image.open(f"{root}/{file}") as im:
                width = im.width
                height = im.height

                # Determine portrait vs landscape
                # We want a minimum pixel size of scale_to_px!!
                aspect_ratio = height / width
                if aspect_ratio < 1.0:
                    aspect_ratio = width / height
                    new_width = int(scale_to_px * aspect_ratio)
                    new_height = scale_to_px
                else:
                    new_width = scale_to_px
                    new_height = int(scale_to_px * aspect_ratio)

                hi_im = im.resize((new_width * 2, new_height * 2))
                lo_im = im.resize((new_width, new_height))

                # Absolutely terrifying, and I'd probably fail my own interview test if I did this in one line with no error checking!
                # Note this will fail on folks who have hyphenated names lol
                new_filename = file.split('-')[-1].split('.')[0].strip().replace(' ', '_').lower()

                for image, filename, scale in [(lo_im, new_filename, scale_to_px), (hi_im, f'{new_filename}-high-res', scale_to_px*2)]:
                    left = (image.width - scale) / 2
                    top = (image.height - scale) / 2
                    right = (image.width + scale) / 2
                    bottom = (image.height + scale) / 2

                    image = image.crop((left, top, right, bottom))

                    image.save(f'../media/img/thunderbird/staff/{filename}.png', format='png')
                    image.save(f'../media/img/thunderbird/staff/{filename}.webp', format='webp')



if __name__ == "__main__":
    handle_crop()
