import booru
import pytest


@pytest.mark.asyncio
async def test_booru_search(custom_pics):
    data = await custom_pics.get_gelbooru(booru.Gelbooru(), "faruzan")
    assert data["file_url"] is not None


@pytest.mark.asyncio
async def test_waifu(custom_pics):
    data = await custom_pics.get_waifu()
    assert data is not None


def test_wolfram(custom_pics):
    data = custom_pics.get_wolfram_simple("2+2", test=True)
    assert data.status_code == 403


def test_openai_moderation_block(custom_pics):
    data = custom_pics.get_openai_img("fucked")
    assert data[0] is False


def test_openai_moderation_allow(custom_pics):
    data = custom_pics.get_openai_img("dog", test=True)
    assert data[0] is True
