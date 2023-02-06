#!/usr/bin/python
import argparse
import sys
import polib
import settings


def main():
    print("Give.thunderbird.net string importer script")

    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', help='Run this script without actually merging any strings', action='store_true', default=False)
    parser.add_argument('--faq-project', help='Root project directory where the strings will be pulled from.', default='../tmp/thunderbird-donate-content')
    parser.add_argument('--ways-to-give-project', default='../tmp/donate-l10n')
    parser.add_argument('--tbnet-project', help='Root project directory where the strings will be merged into.', default='../locale')
    args = parser.parse_args()

    print("Running with --dry-run={}\n".format(args.dry_run))

    locales = settings.FRU_LANGUAGES.keys()

    reference_strings = retrieve_source_strings(args.tbnet_project)

    for locale in locales:
        if 'en-' in locale:
            continue

        # Folders use underscores
        locale = locale.replace('-', '_')

        faq_localized = pull_strings_faq(reference_strings, locale, args.faq_project)
        ways_to_give_localized = pull_strings_ways_to_give(reference_strings, locale, args.ways_to_give_project)

        localized = faq_localized.copy()
        localized.update(ways_to_give_localized)

        if not args.dry_run:
            push_strings(localized, locale, args.tbnet_project)

        print("[{}] {} strings were imported.".format(locale, len(localized)))

    print ("Finished importing strings")


def occurs_in(to_find, occurrences):
    """Occurrences property is a list of tuples, first entry in the tuple is the filename and that's all we need."""
    for occurrence in occurrences:
        if to_find in occurrence[0]:
            return True

    return False


def retrieve_source_strings(directory):
    """Retrieve the source strings for faq.py, ways-to-give.html, and donate/index.html, so we can compare it later."""
    source_po = "{}/templates/LC_MESSAGES/messages.pot".format(directory)

    try:
        po_file = polib.pofile(source_po)
    except IOError:
        print("! Could not load `messages.pot`")
        # We can't proceed if we don't have the source strings...
        sys.exit()

    reference_strings = []

    for entry in po_file:
        if len(entry.occurrences) == 0:
            continue

        conditions = (
            occurs_in('faq.py', entry.occurrences),
            occurs_in('website/includes/ways-to-give.html', entry.occurrences),
            occurs_in('website/donate/index.html', entry.occurrences),
        )

        if not any(conditions):
            continue

        reference_strings.append(entry.msgid)

    return reference_strings


def pull_strings_from_po(filename):
    """Generator to load the file, and yield each entry"""
    try:
        po_file = polib.pofile(filename)
    except IOError:
        print("! Could not load `{}`".format(filename))
        return

    for entry in po_file:
        yield entry


def pull_strings_faq(reference_strings, locale, directory):
    """Compare and retrieve the localized strings from the thunderbird specific faq."""
    faq_po = "{}/locales/{}/pages/mozilla-donate/faq.po".format(directory, locale)

    matched_strings = {}

    for entry in pull_strings_from_po(faq_po):
        if entry.msgid in reference_strings:
            matched_strings[entry.msgid] = entry.msgstr

    return matched_strings


def pull_strings_ways_to_give(reference_strings, locale, directory):
    """Compare and retrieve the localized strings from the thunderbird specific ways to give page."""
    django_po = "{}/donate/locale/{}/LC_MESSAGES/django.po".format(directory, locale)

    matched_strings = {}

    for entry in pull_strings_from_po(django_po):
        if not occurs_in('donate/thunderbird/templates/pages/core/ways_to_give_page.html', entry.occurrences):
            continue

        if entry.msgid in reference_strings:
            matched_strings[entry.msgid] = entry.msgstr

    return matched_strings


def push_strings(localized_strings, locale, directory):
    """Push the retrieved localized strings into their specific messages.po file."""
    localized_po = "{}/{}/LC_MESSAGES/messages.po".format(directory, locale)

    #
    try:
        po_file = polib.pofile(localized_po)
    except IOError:
        print("! Could not load `{}`".format(localized_po))
        return False

    for entry in po_file:
        conditions = (
            occurs_in('faq.py', entry.occurrences),
            occurs_in('website/includes/ways-to-give.html', entry.occurrences),
            occurs_in('website/donate/index.html', entry.occurrences),
        )

        if not any(conditions):
            continue

        # If we have a match, and we're not going to override existing localization...
        if entry.msgid in localized_strings and not entry.msgstr:
            entry.msgstr = localized_strings[entry.msgid]

    po_file.save(localized_po)
    return True


if __name__ == '__main__':
    main()
