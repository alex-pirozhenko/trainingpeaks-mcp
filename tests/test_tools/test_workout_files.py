"""Tests for tp_download_workout_file, including the return_base64 workaround.

return_base64 exists because the file is downloaded into the MCP server's own
filesystem (saved_to), which an MCP client on a different host/container
can't reach (see docs/PROGRESS.md and the sibling garmin-mcp download tool
for the same fix applied there).
"""
import base64
import json
from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import RawResponse
from tp_mcp.tools.workout_files import MAX_BASE64_SOURCE_BYTES, tp_download_workout_file

WORKOUT_ID = "3747106892"
FILE_ID = "863133906"


def _mock_raw_response(content: bytes, content_type: str = "application/octet-stream"):
    return RawResponse(
        success=True,
        content=content,
        content_type=content_type,
        content_disposition='attachment; filename="activity.fit.gz"',
    )


class TestTpDownloadWorkoutFile:
    @pytest.mark.asyncio
    async def test_default_behavior_unchanged_no_base64(self, tmp_path):
        """Without return_base64, response has no content_base64 key (backward compatible)."""
        payload = b"fit file bytes"

        with patch("tp_mcp.tools.workout_files.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get_raw = AsyncMock(return_value=_mock_raw_response(payload))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_download_workout_file(WORKOUT_ID, FILE_ID, output_path=str(tmp_path))

        assert "content_base64" not in result
        assert result["saved_to"] == str((tmp_path / "activity.fit.gz").resolve())

    @pytest.mark.asyncio
    async def test_return_base64_includes_content(self, tmp_path):
        """return_base64=True adds a content_base64 field that round-trips to the same bytes."""
        payload = b"fit file bytes for a client without filesystem access"

        with patch("tp_mcp.tools.workout_files.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get_raw = AsyncMock(return_value=_mock_raw_response(payload))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_download_workout_file(
                WORKOUT_ID, FILE_ID, output_path=str(tmp_path), return_base64=True
            )

        assert base64.b64decode(result["content_base64"]) == payload
        # Saving to disk still happens too (additive, not either/or)
        assert result["saved_to"] == str((tmp_path / "activity.fit.gz").resolve())

    @pytest.mark.asyncio
    async def test_return_base64_over_cap_gets_error_not_huge_payload(self, tmp_path):
        """Files over the 5MB cap get base64_error instead of blowing up the response."""
        payload = b"x" * (MAX_BASE64_SOURCE_BYTES + 1)

        with patch("tp_mcp.tools.workout_files.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get_raw = AsyncMock(return_value=_mock_raw_response(payload))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_download_workout_file(
                WORKOUT_ID, FILE_ID, output_path=str(tmp_path), return_base64=True
            )

        assert "content_base64" not in result
        assert "exceeds the 5 MB" in result["base64_error"]
        # Response stays small even though the underlying file is huge.
        assert len(json.dumps(result)) < 1000
