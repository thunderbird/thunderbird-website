 # -*- coding: utf-8 -*-

from collections import OrderedDict
import json
import os
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


    def get_download_url(self, channel, version, plat_os, locale, force_direct=False):
        return 'https://download.mozilla.org/?product=thunderbird-52.1.1-SSL&os={0}&lang=en-US'.format(plat_os)


thunderbird_desktop = ThunderbirdDetails()
