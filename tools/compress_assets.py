"""
Make sure to install requirements-image.txt!
"""
import argparse
import os

from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument('directory', help='Root directory to search')
parser.add_argument('-r', '--recursive', help='Iterate through every directory found', action='store_true')
parser.add_argument('-o', '--overwrite-existing', help='Ignores existing files, and overwrites them',
                    action='store_true')

args = parser.parse_args()


def compress_image(image_path: str, formats=('webp', 'avif'), overwrite_existing=False):
    """Compresses image_path to the formats in the formats param. Optionally you can overwrite existing files."""
    # We'll build a dict with format as key, and a path as the value.
    formats_exist = {}

    # Fancy filter function, exclude the formats that exist. (Unless we're overwriting them!)
    for format in formats:
        # Remove the extension, and join back any relative pathing we might have nuked
        file_with_new_ext = f"{'.'.join(image_path.rsplit('.')[:-1])}.{format}"
        if os.path.isfile(file_with_new_ext) and not overwrite_existing:
            continue

        formats_exist[format] = file_with_new_ext

    # print(f"Compressing asset {image_path} with following formats: ", formats_exist)

    with Image.open(image_path) as im:
        for format, file_path in formats_exist.items():
            if not file_path:
                continue

            print("Saving", file_path, format)
            im.save(file_path, format)


def main(args):
    print("Compressing assets with the following flags: ", args.__dict__)

    for root, dirs, files in os.walk(args.directory):
        for file in files:
            if any(ext in file for ext in ['png', 'jpg', 'jpeg']):
                compress_image(f"{root}/{file}", overwrite_existing=args.overwrite_existing)

        if not args.recursive:
            break


if __name__ == "__main__":
    main(args)
