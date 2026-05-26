"""
This tool requires Pillow
https://pypi.org/project/pillow/

We don't use it anywhere else so it doesn't really need to be in reqs...

Usage:

Place a list of uncropped photos in /media/img/thunderbird/staff/uncropped

Ensure that they have a name structure like <whatever> - <First Name> <Last Name>.whatever-extension
(e.g. 97147377 - Melissa Autumn.jpg)

And run this script! It will spit out <first name>_<last name>.png/webp, and <first name>_<last name>-high-res.png/webp.

Additionally, I've added some basic cropping alignment, so if someone has [HorzCrop,VertCrop] after their name
(e.g. 97147377 - Melissa Autumn[Center,Top].jpg)

Then it will adjust the origin of the crop. (In that case horizontally centered but starts from the top of the image.)

We don't have fancy pixel offsets, so do some trimming beforehand if the crop isn't perfect.

Photos from phones or design tools often embed wide-gamut ICC profiles (e.g. Display P3). Color-managed
apps (macOS Preview) render those correctly; many editors and browsers treat untagged-looking RGB as
sRGB and look washed out. This script converts embedded profiles to sRGB before resize/crop.

"""
import enum
import os
import re
from io import BytesIO

from PIL import Image, ImageCms, ImageOps

scale_to_px = 128

_srgb_profile = ImageCms.createProfile('sRGB')
_srgb_icc_bytes = ImageCms.ImageCmsProfile(_srgb_profile).tobytes()


def ensure_srgb(image: Image.Image) -> Image.Image:
    """Convert embedded ICC profiles to sRGB for consistent web and editor display."""
    icc = image.info.get('icc_profile')
    if not icc:
        return image

    try:
        src_profile = ImageCms.ImageCmsProfile(BytesIO(icc))
        converted = ImageCms.profileToProfile(
            image, src_profile, _srgb_profile, outputMode='RGB'
        )
    except (ImageCms.PyCMSError, OSError, ValueError) as err:
        print(f"Warning: could not convert color profile ({err}); using source pixels as-is")
        return image

    converted.info['icc_profile'] = _srgb_icc_bytes
    return converted


def save_staff_image(image: Image.Image, path: str, *, file_format: str) -> None:
    save_kwargs = {}
    if icc := image.info.get('icc_profile'):
        save_kwargs['icc_profile'] = icc
    image.save(path, format=file_format, **save_kwargs)


class HorzCropCommands(enum.StrEnum):
    LEFT = 'left'
    CENTER = 'center'
    RIGHT = 'right'


class VertCropCommands(enum.StrEnum):
    TOP = 'top'
    CENTER = 'center'
    BOTTOM = 'bottom'


def process_crop_command(image: Image, scale: int, horz=HorzCropCommands.CENTER, vert=VertCropCommands.CENTER):
    """Takes in horizontal crop and vertical crop params, and crops the image. I've only ever tested center,top btw."""
    left = 0
    top = 0
    right = 0
    bottom = 0

    print(f"Cropping - [H={horz},V={vert}]")

    if horz == HorzCropCommands.CENTER:
        left = (image.width - scale) / 2
        right = (image.width + scale) / 2
    elif horz == HorzCropCommands.LEFT:
        left = 0
        right = scale
    elif horz == HorzCropCommands.RIGHT:
        left = (image.width - scale)
        right = image.width

    if vert == VertCropCommands.CENTER:
        top = (image.height - scale) / 2
        bottom = (image.height + scale) / 2
    elif vert == VertCropCommands.TOP:
        top = 0
        bottom = scale
    elif vert == VertCropCommands.BOTTOM:
        top = (image.height - scale)
        bottom = image.height

    return image.crop((left, top, right, bottom))


def handle_crop():
    """A messy script to load in all the images in uncropped, resize them to scale_to_px (and scale_to_px*2 for @2x) and centre crop them to be square!
    Expects staff names in image like `this is ignored - Melissa Autumn.jpg` -> `melissa-autumn.png"""

    special_crop_command_regex = r"\[([\w]*\,[\w]*)\]"

    for root, dirs, files in os.walk('../media/img/thunderbird/staff/uncropped'):
        for file in files:
            if not file.lower().endswith(('.png', 'jpeg', '.jpg', '.webm')):
                continue
            print(f"{root}/{file}")
            with Image.open(f"{root}/{file}") as im:
                im = ImageOps.exif_transpose(im)
                im = ensure_srgb(im)
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

                # Special crop command
                match = re.findall(special_crop_command_regex, new_filename)
                crop_commands = ['center', 'center']
                if len(match) > 0:
                    crop_commands = match[0].split(',')
                    new_filename = new_filename.replace(f"[{match[0]}]", "")

                for image, filename, scale in [(lo_im, new_filename, scale_to_px),
                                               (hi_im, f'{new_filename}-high-res', scale_to_px * 2)]:
                    image = process_crop_command(image, scale, crop_commands[0], crop_commands[1])

                    out_dir = '../media/img/thunderbird/staff'
                    save_staff_image(image, f'{out_dir}/{filename}.png', file_format='png')
                    save_staff_image(image, f'{out_dir}/{filename}.webp', file_format='webp')


if __name__ == "__main__":
    handle_crop()
