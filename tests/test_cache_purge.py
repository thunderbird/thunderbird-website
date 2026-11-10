import cache_purge

START = "start.thunderbird.net"
ADDONS = "addons.thunderbird.net"
WWW = "www.thunderbird.net"
UPDATES = "updates.thunderbird.net"
TBPRO = "tb.pro"
WWW_TBPRO = "www.tb.pro"
ROADMAPS = "roadmaps.thunderbird.net"
ROADMAP = "roadmap.thunderbird.net"

START_RULES = [
    ("start.thunderbird.net/", [START]),
    ("start.thunderbird.net/en-US/maintenance/", [ADDONS]),
]
SHARED_FILE_RULES = [
    ("wsgi.py", [WWW, UPDATES, TBPRO, WWW_TBPRO, ROADMAPS, ROADMAP]),
]


def _pages(**paths):
    """Build a snapshot from path/text pairs."""
    return {path: text.encode() for path, text in paths.items()}


class TestChangedHostnames:
    def test_equal_snapshots_and_empty_snapshots_select_nothing(self):
        """Unchanged files, including two empty snapshots, affect no hostnames."""
        snapshot = _pages(**{"start.thunderbird.net/en-US/index.html": "same"})

        assert cache_purge.changed_hostnames(snapshot, dict(snapshot), START_RULES) == set()
        assert cache_purge.changed_hostnames({}, {}, START_RULES) == set()

    def test_changed_added_and_deleted_files_select_their_site(self):
        """Byte edits, new files, and removed files all select the mapped site."""
        before = _pages(**{
            "www.thunderbird.net/en-US/index.html": "old",
            "www.thunderbird.net/en-US/gone.html": "gone",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/index.html": "new",
            "www.thunderbird.net/en-US/added.html": "added",
        })
        rules = [("www.thunderbird.net/", [WWW])]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW}

    def test_empty_file_addition_and_deletion_select_the_site(self):
        """A zero-byte file counts when it appears or disappears."""
        path = "www.thunderbird.net/empty.txt"
        rules = [("www.thunderbird.net/", [WWW])]

        assert cache_purge.changed_hostnames({}, {path: b""}, rules) == {WWW}
        assert cache_purge.changed_hostnames({path: b""}, {}, rules) == {WWW}
        assert cache_purge.changed_hostnames({path: b""}, {path: b""}, rules) == set()

    def test_changes_in_several_directories_select_each_site(self):
        """Independent directory changes select every site those rules name."""
        before = _pages(**{
            "www.thunderbird.net/en-US/index.html": "www",
            "updates.thunderbird.net/en-US/index.html": "updates",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/index.html": "www changed",
            "updates.thunderbird.net/en-US/index.html": "updates changed",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}

    def test_maintenance_change_selects_start_and_addons(self):
        """The maintenance prefix and the broader start prefix both contribute."""
        path = "start.thunderbird.net/en-US/maintenance/index.html"
        before = _pages(**{path: "down"})
        after = _pages(**{path: "still down"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START, ADDONS}

    def test_other_start_path_selects_start_only(self):
        """A start page outside en-US maintenance does not select addons."""
        path = "start.thunderbird.net/en-US/release/index.html"
        before = _pages(**{path: "release"})
        after = _pages(**{path: "release changed"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START}

    def test_other_locale_maintenance_selects_start_only(self):
        """Addons serves the en-US maintenance directory, not other locales."""
        path = "start.thunderbird.net/fr/maintenance/index.html"
        before = _pages(**{path: "maintenance"})
        after = _pages(**{path: "maintenance changed"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == {START}

    def test_exact_shared_file_selects_every_assigned_hostname(self):
        """An exact file rule contributes each hostname listed for that file."""
        before = _pages(**{"wsgi.py": "redirect-a"})
        after = _pages(**{"wsgi.py": "redirect-b"})

        assert cache_purge.changed_hostnames(before, after, SHARED_FILE_RULES) == {
            WWW, UPDATES, TBPRO, WWW_TBPRO, ROADMAPS, ROADMAP,
        }

    def test_rename_between_sites_selects_both_sites(self):
        """A rename is a deletion on the old site and an addition on the new site."""
        before = _pages(**{"www.thunderbird.net/en-US/moved.html": "page"})
        after = _pages(**{"updates.thunderbird.net/en-US/moved.html": "page"})
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}

    def test_repeated_hostname_is_returned_once(self):
        """Several changed paths that share a hostname produce one result entry."""
        before = _pages(**{
            "www.thunderbird.net/en-US/one.html": "one",
            "www.thunderbird.net/en-US/two.html": "two",
        })
        after = _pages(**{
            "www.thunderbird.net/en-US/one.html": "one changed",
            "www.thunderbird.net/en-US/two.html": "two changed",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("www.thunderbird.net/en-US/", [WWW]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW}

    def test_exact_file_and_directory_rules_respect_path_boundaries(self):
        """Similar names do not match an exact file or a directory prefix."""
        rules = [
            ("wsgi.py", [WWW]),
            ("start.thunderbird.net/", [START]),
            ("start.thunderbird.net/en-US/maintenance/", [ADDONS]),
        ]
        unchanged = "same"
        # These share a name with a rule but are not that file or inside that directory.
        non_matches = [
            "wsgi.py.bak",
            "includes/wsgi.py",
            "start.thunderbird.net-preview/index.html",
        ]
        before = _pages(**{path: unchanged for path in non_matches})
        after = _pages(**{path: "changed" for path in non_matches})

        assert cache_purge.changed_hostnames(before, after, rules) == set()

        # The parent directory matches; the maintenance directory stops at its slash.
        maintenance_lookalike = "start.thunderbird.net/en-US/maintenance-old/index.html"
        assert cache_purge.changed_hostnames(
            _pages(**{maintenance_lookalike: "old"}),
            _pages(**{maintenance_lookalike: "new"}),
            rules,
        ) == {START}

        exact = _pages(**{"wsgi.py": "old"})
        assert cache_purge.changed_hostnames(exact, _pages(**{"wsgi.py": "new"}), rules) == {WWW}

    def test_unmatched_paths_and_empty_rules_select_nothing(self):
        """Changes outside every rule, and any change with no rules, are ignored."""
        before = _pages(**{"notes/private.txt": "old"})
        after = _pages(**{"notes/private.txt": "new"})

        assert cache_purge.changed_hostnames(before, after, START_RULES) == set()
        assert cache_purge.changed_hostnames(before, after, []) == set()

    def test_timestamp_and_css_byte_changes_select_their_sites(self):
        """Feed timestamps and CSS bytes are ordinary content changes."""
        atom = "www.thunderbird.net/en-US/thunderbird/releases/atom.xml"
        css = "updates.thunderbird.net/media/css/whatsnew-140.css"
        before = _pages(**{
            atom: "<updated>2026-11-10T00:10:49+00:00</updated>",
            css: ".particle-star { opacity: calc(61/100); }",
        })
        after = _pages(**{
            atom: "<updated>2026-11-10T00:35:59+00:00</updated>",
            css: ".particle-star { opacity: calc(5/100); }",
        })
        rules = [
            ("www.thunderbird.net/", [WWW]),
            ("updates.thunderbird.net/", [UPDATES]),
        ]

        assert cache_purge.changed_hostnames(before, after, rules) == {WWW, UPDATES}
