import booru
import pytest


@pytest.mark.asyncio
async def test_booru_search(custom_pics):
    data = await custom_pics.get_gelbooru(booru.Gelbooru(), "eula")
    assert data["file_url"] is not None


@pytest.mark.asyncio
async def test_waifu(custom_pics):
    data = await custom_pics.get_waifu()
    assert data is not None
