import datetime
import os
import xml.etree.ElementTree as ET

import builder
import settings

ATOM = {"a": "http://www.w3.org/2005/Atom"}


def release_note(release_date, text):
    return {
        "release": {
            "release_date": release_date,
            "groups": [None],
        },
        "notes": [{"note": text, "tag": "new", "group": 1}],
        "known_issues": [],
    }


def feed_file(site):
    return os.path.join(site.outpath, "thunderbird", "releases", "atom.xml")


def render_feed(site, items):
    site.build_notes_feed(items)
    return open(feed_file(site), encoding="utf-8").read()


def parsed_feed(xml):
    root = ET.fromstring(xml)
    entries = []
    for entry in root.findall("a:entry", ATOM):
        entries.append({
            "title": entry.find("a:title", ATOM).text,
            "published": entry.find("a:published", ATOM).text,
            "updated": entry.find("a:updated", ATOM).text,
            "content": entry.find("a:content", ATOM).text,
        })
    return root.find("a:updated", ATOM).text, entries


class TestNotesFeed:
    def setup_method(self):
        self.dates = {}

    def _site(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            builder.thunderbird_desktop,
            "get_release_date",
            lambda version: self.dates.get(version, ""),
        )
        site = builder.Site(["en-US"], settings.WEBSITE_PATH, str(tmp_path), {})
        site._switch_lang("en-US")
        os.makedirs(os.path.join(site.outpath, "thunderbird", "releases"))
        return site

    def test_unchanged_notes_keep_the_same_feed_timestamp(self, tmp_path, monkeypatch):
        """The feed timestamp comes from release dates, not the build clock."""
        site = self._site(tmp_path, monkeypatch)
        items = [("1.0", release_note(datetime.datetime(2024, 1, 10), "Original note"))]
        site._env.globals["NOW"] = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        first = render_feed(site, items)
        site._env.globals["NOW"] = datetime.datetime(2030, 6, 1, tzinfo=datetime.UTC)
        second = render_feed(site, items)

        assert first == second
        updated, entries = parsed_feed(first)
        assert updated == "2024-01-10T00:00:00+00:00"
        assert "2020-01-01" not in first
        assert "2030-06-01" not in first
        assert entries[0]["published"] == "2024-01-10T00:00:00+00:00"
        assert entries[0]["updated"] == "2024-01-10T00:00:00+00:00"

    def test_changed_release_date_moves_the_feed_timestamp(self, tmp_path, monkeypatch):
        """A newer included release date becomes the feed timestamp."""
        site = self._site(tmp_path, monkeypatch)
        older = release_note(datetime.datetime(2024, 1, 10), "Older release")
        newer = release_note(datetime.datetime(2024, 5, 1), "Newer release")
        updated, entries = parsed_feed(render_feed(site, [("1.0", older), ("2.0", newer)]))

        assert [entry["title"] for entry in entries] == ["Thunderbird 2.0", "Thunderbird 1.0"]
        assert entries[0]["published"] == "2024-05-01T00:00:00+00:00"
        assert entries[1]["published"] == "2024-01-10T00:00:00+00:00"
        assert updated == "2024-05-01T00:00:00+00:00"

        newer["release"]["release_date"] = datetime.datetime(2024, 8, 1)
        updated, entries = parsed_feed(render_feed(site, [("1.0", older), ("2.0", newer)]))
        assert [entry["title"] for entry in entries] == ["Thunderbird 2.0", "Thunderbird 1.0"]
        assert entries[0]["updated"] == "2024-08-01T00:00:00+00:00"
        assert updated == "2024-08-01T00:00:00+00:00"

    def test_product_details_date_is_the_entry_update(self, tmp_path, monkeypatch):
        """Product-details supplies entry updates and can move the feed timestamp without reordering."""
        self.dates = {"1.0": "2024-01-11", "2.0": "2024-05-02"}
        site = self._site(tmp_path, monkeypatch)
        older = release_note(datetime.datetime(2024, 1, 10), "Older release")
        newer = release_note(datetime.datetime(2024, 5, 1), "Newer release")
        updated, entries = parsed_feed(render_feed(site, [("1.0", older), ("2.0", newer)]))

        assert [entry["title"] for entry in entries] == ["Thunderbird 2.0", "Thunderbird 1.0"]
        assert entries[0]["published"] == "2024-05-01T00:00:00+00:00"
        assert entries[0]["updated"] == "2024-05-02T00:00:00+00:00"
        assert entries[1]["published"] == "2024-01-10T00:00:00+00:00"
        assert entries[1]["updated"] == "2024-01-11T00:00:00+00:00"
        assert updated == "2024-05-02T00:00:00+00:00"

        self.dates["1.0"] = "2024-08-01"
        updated, entries = parsed_feed(render_feed(site, [("1.0", older), ("2.0", newer)]))
        assert [entry["title"] for entry in entries] == ["Thunderbird 2.0", "Thunderbird 1.0"]
        assert entries[1]["updated"] == "2024-08-01T00:00:00+00:00"
        assert updated == "2024-08-01T00:00:00+00:00"

    def test_note_text_changes_the_entry_but_not_the_timestamp(self, tmp_path, monkeypatch):
        """Note text is rendered, but it has no date, so the feed timestamp stays put."""
        site = self._site(tmp_path, monkeypatch)
        note = release_note(datetime.datetime(2024, 5, 1), "Original wording")
        first_updated, first_entries = parsed_feed(render_feed(site, [("2.0", note)]))
        assert "Original wording" in first_entries[0]["content"]

        note["notes"][0]["note"] = "Revised wording"
        second_updated, second_entries = parsed_feed(render_feed(site, [("2.0", note)]))
        assert "Revised wording" in second_entries[0]["content"]
        assert "Original wording" not in second_entries[0]["content"]
        assert second_updated == first_updated
        assert second_entries[0]["published"] == first_entries[0]["published"]
        assert second_entries[0]["updated"] == first_entries[0]["updated"]

    def test_empty_feed_writes_nothing(self, tmp_path, monkeypatch):
        """No release notes still produces no atom file."""
        site = self._site(tmp_path, monkeypatch)
        site.build_notes_feed([])
        assert not os.path.exists(feed_file(site))
