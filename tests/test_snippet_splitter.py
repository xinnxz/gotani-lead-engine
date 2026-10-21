"""Test anti-kontaminasi: Google snippet gabungan harus dipecah."""
import pytest
from agent.executors.fb import _split_google_snippet


class TestSnippetSplitter:
    """Test pemisahan snippet Google Search yang mengandung >1 post FB."""

    def test_single_post_no_split(self):
        """Post tunggal tidak dipecah."""
        title = "Forum Jual Beli Seruyan"
        snippet = "Bismillah. SDH ready 20 okt 26. Semangka manis merah dan kuning dri tmbak sgntung. Seruyan Kuala pembuang."
        result = _split_google_snippet(title, snippet, "https://fb.com/post1")
        assert len(result) == 1
        assert "Bismillah" in result[0]["text"]

    def test_merged_snippet_splits(self):
        """Snippet gabungan 2 post harus dipecah menjadi 2."""
        title = "Forum Jual Beli Seruyan"
        snippet = (
            "Bismillah. SDH ready 20 okt 26. Semangka manis merah dan kuning dri tmbak sgntung. "
            "Seruyan Kuala pembuang. ... "
            "Jual semangka kuning, melon, dan mangga segar di Sangatta. Nandhini ready semangka merah 10k dapat 3 Wa 085731478422 Lokasi Namira."
        )
        result = _split_google_snippet(title, snippet, "https://fb.com/post1")
        assert len(result) >= 2, f"Seharusnya dipecah jadi 2+, tapi dapat {len(result)}: {result}"
        
        # Post pertama harus mengandung "Bismillah" (Yulia Amanda)
        assert "Bismillah" in result[0]["text"]
        # Post pertama TIDAK boleh mengandung nomor HP orang lain
        assert "085731478422" not in result[0]["text"]

    def test_short_snippet_no_split(self):
        """Snippet pendek tidak dipecah."""
        result = _split_google_snippet("Title", "Short text here", "url")
        assert len(result) == 1

    def test_empty_snippet(self):
        """Snippet kosong tidak error."""
        result = _split_google_snippet("Title", "", "url")
        assert len(result) == 1
