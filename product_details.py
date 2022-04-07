# -*- coding: utf-8 -*-

from collections import OrderedDict
from operator import itemgetter
import sys
if sys.version_info[0] == 3:
    from urllib.parse import urlencode
else:
    from urllib import urlencode

import json
import os
import re
import settings


def load_json(path):
    """Load the .json at `path` and return data."""
    path = os.path.join(settings.JSON_PATH, path)
    with open(path, 'r') as f:
        return json.load(f)


class ThunderbirdDetails():
    """ Loads Thunderbird versioning information from product details JSON files."""
    platform_labels = OrderedDict([
        # ('winsha1', 'Windows (XP/Vista)'),
        ('win64', 'Windows 64-bit'),
        ('msi', 'Windows MSI 64-bit'),
        ('osx', 'macOS'),
        ('linux64', 'Linux 64-bit'),
        ('win', 'Windows 32-bit'),
        ('linux', 'Linux 32-bit')
    ])

    languages = load_json('languages.json')

    current_versions = load_json('thunderbird_versions.json')

    all_builds = load_json('thunderbird_primary_builds.json')

    major_releases = load_json('thunderbird_history_major_releases.json')

    minor_releases = load_json('thunderbird_history_stability_releases.json')

    major_releases = load_json('thunderbird_history_major_releases.json')

    dev_releases = load_json('thunderbird_history_development_releases.json')

    version_map = {
        'daily': 'LATEST_THUNDERBIRD_NIGHTLY_VERSION',
        'beta': 'LATEST_THUNDERBIRD_DEVEL_VERSION',
        'release': 'LATEST_THUNDERBIRD_VERSION',
    }

    def latest_version(self, channel='release'):
        """Returns the latest release version of Thunderbird by default, or other `channel`."""
        version_name = self.version_map.get(channel, 'LATEST_THUNDERBIRD_VERSION')
        return self.current_versions[version_name]

    def latest_builds(self, locale, channel='release'):
        """Returns builds for the latest version of Thunderbird based on `channel`."""
        version = self.latest_version(channel)

        all_builds = self.all_builds
        if locale in all_builds and version in all_builds[locale]:
            builds = all_builds[locale][version]
            # Append 64-bit builds
            if 'Linux' in builds:
                builds['Linux 64-bit'] = builds['Linux']
            if 'Windows' in builds:
                builds['Windows 64-bit'] = builds['Windows']
            return version, builds

    def get_filtered_full_builds(self, channel, version):
        version = version or self.latest_version(channel)
        f_builds = []
        builds = self.all_builds

        for locale, build in builds.items():

            if locale not in self.languages or not build.get(version):
                continue

            build_info = {
                'locale': locale,
                'name_en': self.languages[locale]['English'],
                'name_native': self.languages[locale]['native'],
                'platforms': {},
            }

            for platform, label in self.platform_labels.items():
                build_info['platforms'][platform] = {
                    'download_url': self.get_download_url(channel, version,
                                                          platform, locale,
                                                          True),
                }

            f_builds.append(build_info)

        return sorted(f_builds, key=itemgetter('name_en'))

    def get_download_url(self, channel, version, platform, locale, force_direct=True):
        _version = version
        _locale = 'ja-JP-mac' if platform == 'osx' and locale == 'ja' else locale
        _platform = 'win' if platform == 'winsha1' else platform
        product_url = 'thunderbird-%s-SSL'

        if platform == 'msi':
            _platform = 'win64'
            product_url = 'thunderbird-%s-msi-SSL'

        # Check if direct download link has been requested
        # (bypassing the transition page)
        if not force_direct:
            # Currently we don't have the transition page for Thunderbird, so
            # return a direct link instead
            pass

        # The 'daily' channel is hosted on FTP and uses a different filename format.
        if channel == 'daily':
            platform_filetype = {
                'osx': 'mac.dmg',
                'linux': 'linux-i686.tar.bz2',
                'linux64': 'linux-x86_64.tar.bz2',
                'win': 'win32.installer.exe',
                'win64': 'win64.installer.exe'
            }
            platform_filename = platform_filetype.get(_platform, '')
            daily_url = 'thunderbird-{version}.{locale}.{platform}'.format(version=_version, locale=_locale, platform=platform_filename)
            return ''.join([settings.DAILY_URL, daily_url])

        # build a direct download link for 'beta' and 'release' channels.
        return '?'.join([settings.BOUNCER_URL,
                         urlencode([
                             ('product', product_url % _version),
                             ('os', _platform),
                             # Order matters, lang must be last for bouncer.
                             ('lang', _locale),
                         ])])

    def platforms(self, channel='release'):
        return self.platform_labels.items()

    def list_releases(self, channel='beta'):
        version_name = self.version_map.get(channel, 'LATEST_THUNDERBIRD_DEVEL_VERSION')
        esr_major_versions = (
            list(range(10, 59, 7))
            + [60, 68]
            + list(range(78, int(self.current_versions[version_name].split('.')[0]) + 1, 13))
        )
        releases = {}
        for release in self.major_releases:
            major_version = float(re.findall(r'^\d+\.\d+', release)[0])
            # The version numbering scheme of Firefox changes sometimes. The second
            # number has not been used since Firefox 4, then reintroduced with
            # Firefox ESR 24 (Bug 870540). On this index page, 24.1.x should be
            # fallen under 24.0. This pattern is a tricky part.
            converter = '%g' if int(major_version) in esr_major_versions else '%s'
            major_pattern = r'^' + re.escape(converter % round(major_version, 1))
            releases[major_version] = {
                'major': release,
                'minor': sorted(filter(lambda x: re.findall(major_pattern, x),
                                       self.minor_releases),
                                key=lambda x: list(map(lambda y: int(y), x.split('.'))))
            }
        return sorted(releases.items(), reverse=True)

    def beta_version_to_canonical(self, version):
        last = ''
        for x in range(1, 10):
            v = re.sub(r'beta', 'b{0}'.format(x), version)
            date = self.dev_releases.get(v, '')
            if date:
                last = v
        return last

    def get_release_date(self, version):
        date = ''
        if 'b' in version:
            version = self.beta_version_to_canonical(version)
            date = self.dev_releases.get(version, '')

        if not date:
            date = self.major_releases.get(version, '')

        if not date:
            date = self.minor_releases.get(version, '')

        return date


thunderbird_desktop = ThunderbirdDetails()
