# -*- coding: utf-8 -*-

from collections import OrderedDict
from operator import itemgetter
from urllib.parse import urlencode
import json
import os
import re
import settings


def filter_major_versions(versions):
    """Filters out some version numbers not meant for human consumption."""
    # Preserves json ordering
    for version in settings.VERSIONS_TO_FILTER:
        if version in versions:
            del versions[version]

    return versions


def load_json(path):
    """Load the .json at `path` and return data."""
    path = os.path.join(settings.JSON_PATH, path)
    with open(path, 'r') as f:
        return json.load(f)


def load_all_builds(path):
    """ Loads the all_builds data, and mixes in the latest beta information with all release locales. """
    all_builds = load_json(path)

    # We heavily rely on en-US, but if somehow that's no longer a locale, at least don't crash here.
    if 'en-US' not in all_builds:
        return all_builds

    all_data = {}

    # Filter just the beta builds
    for build, info in all_builds.get('en-US').items():
        if 'b' in build:
            all_data.update({build: info})

    for locale, build in all_builds.items():
        # Already has beta information
        if locale == 'en-US':
            continue
        # Merge the beta build information
        all_builds[locale].update(all_data)

    return all_builds


class ThunderbirdDetails():
    """ Loads Thunderbird versioning information from product details JSON files."""
    platform_labels = OrderedDict([
        # ('winsha1', 'Windows (XP/Vista)'),
        ('win64', 'Windows 64-bit'),
        ('msi', 'Windows MSI 64-bit'),
        ('osx', 'macOS'),
        ('linux64', 'Linux 64-bit'),
        ('win', 'Windows 32-bit'),
        ('linux', 'Linux 32-bit'),
        ('win8-64', 'Windows 64-bit (7/8.1)'),
        ('win8', 'Windows 32-bit (7/8.1)'),
    ])

    # Grouped by platform
    grouped_platform_labels = OrderedDict({
        'Windows': [('win64', '64-bit (.exe)'), ('msi', '64-bit (.msi)'), ('win', '32-bit (.exe)')],
        'Windows (7/8.1)': [('win8-64', '64-bit (.exe)'), ('win8', '32-bit (.exe)')],
        'Linux': [('linux64', '64-bit (binary)'), ('linux', '32-bit (binary)')],
        'macOS': [('osx', '64-bit (.dmg)')]
    })

    languages = load_json('languages.json')

    releases: dict = load_json('thunderbird.json')

    current_versions = load_json('thunderbird_versions.json')

    all_builds = load_all_builds('thunderbird_primary_builds.json')

    major_releases = filter_major_versions(load_json('thunderbird_history_major_releases.json'))

    minor_releases = load_json('thunderbird_history_stability_releases.json')

    dev_releases = load_json('thunderbird_history_development_releases.json')

    version_map = {
        'daily': ('LATEST_THUNDERBIRD_NIGHTLY_VERSION',),
        'beta': ('LATEST_THUNDERBIRD_DEVEL_VERSION',),
        'release': ('THUNDERBIRD_ESR_NEXT', 'THUNDERBIRD_ESR'),
        # Win7/8.1 only support up to 115
        'release_win7_8': ('THUNDERBIRD_ESR',)
    }

    channel_labels = OrderedDict({
        'release': 'Release',
        'beta': 'Beta',
        'daily': 'Daily'
    })

    def latest_version(self, channel='release'):
        """Returns the latest release version of Thunderbird by default, or other `channel`."""
        # Force release by default
        version_names = self.version_map.get(channel or 'release')

        version = self.current_versions.get(version_names[0])
        # ESR_NEXT can be an empty string, so we have to fallback to ESR
        if len(version_names) > 1 and version == '':
            version = self.current_versions.get(version_names[1])

        return version

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
        """Retrieve the download url for a given channel, version, platform and locale."""
        _version = version
        _locale = 'ja-JP-mac' if platform == 'osx' and locale == 'ja' else locale
        _platform = 'win' if platform == 'winsha1' else platform
        product_url = 'thunderbird-%s-SSL'

        if channel == 'daily':
            _version = 'nightly-latest'

        if platform == 'msi':
            _platform = 'win64'
            # Daily's bouncer link doesn't support `-msi-SSL`, so we'll just make it a win64 build for now.
            if channel != 'daily':
                product_url = 'thunderbird-%s-msi-SSL'

        if platform == 'win8-64':
            _platform = 'win64'
            _version = self.latest_version('release_win7_8')
        elif platform == 'win8':
            _platform = 'win'
            _version = self.latest_version('release_win7_8')

        # Check if direct download link has been requested
        # (bypassing the transition page)
        if not force_direct:
            # Currently we don't have the transition page for Thunderbird, so
            # return a direct link instead
            pass

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

    def list_releases(self):
        releases = {}

        def needs_esr_fixup(version_ints: list[int]):
            """115.10.2 up until 128.0esr are mislabelled and should be esr builds"""
            if version_ints[0] != 115:
                return False

            # If >=115.11
            if version_ints[1] >= 11:
                return True
            # If >=115.10.2
            elif len(version_ints) >= 2 and version_ints[1] == 10 and version_ints[2] >= 2:
                return True

            return False

        # Split off release and esr builds into major and minor
        major_versions = []
        minor_versions = []
        for key, data in self.releases['releases'].items():
            category: str = data.get('category')
            version: str = data.get('version')

            # Ignore dev releases or anything we want filtered
            if category == 'dev' or version in settings.VERSIONS_TO_FILTER:
                continue

            version_int = [int(y) for y in version.split('.')]

            is_major = category == 'major'
            is_stability = category == 'stability'
            # We only count 128.0 and up as esr (and specific 115.0 versions)
            is_esr = (category == 'esr' and version_int[0] >= 128) or needs_esr_fixup(version_int)

            if is_esr:
                version = f'{version}esr'

            if (is_major or is_esr) and version.count('.') == 1:
                major_versions.append((version, version_int))
            elif is_stability or is_esr:
                minor_versions.append((version, version_int))

        for release in major_versions:
            major_version = float(release[1][0])
            # The version numbering scheme of Thunderbird has changed over the years,
            # so there is some trickiness on major versions below 5.
            # When updating this sorting, be careful old versions aren't broken.
            if major_version < 5:
                major_pattern = release[0] + '.'
            else:
                major_pattern = release[0].split('.')[0] + '.'

            # Reparse the float. Fixes 1.5 releases being merged in with 1.0...
            major_version = float(f"{major_pattern.strip('.')}")

            releases[major_version] = {
                'major': release[0],
                'minor': sorted([x for x in minor_versions
                                 if x[0].startswith(major_pattern)],
                                 key=lambda x: [int(y) for y in x[1]])
            }

            # We returned a tuple, so we could sort properly.
            # Now remake that list and select the string from the tuple.
            releases[major_version]['minor'] = list(map(lambda x: x[0], releases[major_version]['minor']))

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


class ThunderbirdMobileDetails():
    """Shim for Thunderbird Mobile."""
    platform_labels = OrderedDict([
        ('gplay', 'Google Play Store'),
        ('fdroid', 'F-Droid'),
        ('apk', 'Binary')
    ])

    # Grouped by platform
    grouped_platform_labels = OrderedDict({
        'Android': [('gplay', 'Google Play Store'), ('fdroid', 'F-Droid'), ('apk', 'Binary (.apk)')],
    })

    version_map = {
        'release': 'LATEST_THUNDERBIRD_VERSION',
    }

    channel_labels = OrderedDict({
        'mobile': 'Mobile',
    })

    def get_download_url(self, channel, version, platform, locale, force_direct=True):
        """Retrieve the download url for a given channel, version, platform and locale."""

        # Nice and simple
        if platform == 'gplay':
            return settings.URL_MAPPINGS.get('download.android.gplay')
        elif platform == 'fdroid':
            return settings.URL_MAPPINGS.get('download.android.fdroid')
        else:
            return settings.URL_MAPPINGS.get('download.android.binary')


thunderbird_desktop = ThunderbirdDetails()
thunderbird_mobile = ThunderbirdMobileDetails()
