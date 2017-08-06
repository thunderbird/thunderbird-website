 # -*- coding: utf-8 -*-

from collections import OrderedDict
from operator import itemgetter
from urllib import urlencode

import json
import os
import re
import settings

def load_json(path):
    path = os.path.join(settings.JSON_PATH, path)
    with open(path, 'r') as f:
        return json.load(f)

class ThunderbirdDetails():

    platform_labels = OrderedDict([
        ('winsha1', 'Windows (XP/Vista)'),
        ('win', 'Windows'),
        ('osx', 'macOS'),
        ('linux', 'Linux'),
        ('linux64', 'Linux 64-bit'),
    ])

    languages = load_json('languages.json')

    current_versions = load_json('thunderbird_versions.json')

    all_builds = load_json('thunderbird_primary_builds.json')

    major_releases = load_json('thunderbird_history_major_releases.json')

    minor_releases = load_json('thunderbird_history_stability_releases.json')

    version_map = {
        'alpha': 'LATEST_THUNDERBIRD_ALPHA_VERSION',
        'beta': 'LATEST_THUNDERBIRD_DEVEL_VERSION',
        'release': 'LATEST_THUNDERBIRD_VERSION',
    }


    def latest_version(self, channel='release'):
        version_name = self.version_map.get(channel, 'LATEST_THUNDERBIRD_VERSION')
        return self.current_versions[version_name]


    def latest_builds(self, locale, channel='release'):
        version = self.latest_version(channel)

        # We don't really have any build data for non-release builds
        _version = self.latest_version('release')

        builds = self.all_builds
        if locale in builds and _version in builds[locale]:
            _builds = builds[locale][_version]
            # Append 64-bit builds
            if 'Linux' in _builds:
                _builds['Linux 64-bit'] = _builds['Linux']
            return version, _builds


    def get_filtered_full_builds(self, channel, version):
        version = version or self.latest_version(channel)
        _version = self.latest_version('release')
        f_builds = []
        builds = self.all_builds

        for locale, build in builds.iteritems():

            if locale not in self.languages or not build.get(_version):
                continue

            build_info = {
                'locale': locale,
                'name_en': self.languages[locale]['English'],
                'name_native': self.languages[locale]['native'],
                'platforms': {},
            }

            for platform, label in self.platform_labels.iteritems():
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

        # Check if direct download link has been requested
        # (bypassing the transition page)
        if not force_direct:
            # Currently we don't have the transition page for Thunderbird, so
            # return a direct link instead
            pass

        # build a direct download link
        return '?'.join([settings.BOUNCER_URL,
                         urlencode([
                             ('product', 'thunderbird-%s-SSL' % _version),
                             ('os', _platform),
                             # Order matters, lang must be last for bouncer.
                             ('lang', _locale),
                         ])])

    def platforms(self, channel='release'):
        return self.platform_labels.items()


    def list_releases(self, channel='beta'):
        version_name = self.version_map.get(channel, 'LATEST_THUNDERBIRD_DEVEL_VERSION')
        esr_major_versions = range(10, int(self.current_versions[version_name].split('.')[0]), 7)
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
                                key=lambda x: map(lambda y: int(y), x.split('.')))
            }
        return sorted(releases.items(), reverse=True)


    def get_release_date(self, version):
        date = self.major_releases.get(version, '')
        if not date:
            date = self.minor_releases.get(version, '')
        return date


thunderbird_desktop = ThunderbirdDetails()
