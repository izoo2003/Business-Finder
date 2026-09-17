"""Operator-facing signup links and steps for rotating API keys."""

from __future__ import annotations

from typing import TypedDict


class ProviderGuide(TypedDict):
    signup_url: str
    steps: list[str]
    warning: str
    needs_key: bool


GUIDES: dict[str, ProviderGuide] = {
    "google-places": {
        "signup_url": "https://console.cloud.google.com/google/maps-apis/credentials",
        "needs_key": True,
        "warning": (
            "A new key in the same Google Cloud project still shares the free limit. "
            "Sign in with a new Google account, create a new Cloud project, enable "
            "Places API (New), then paste that key here."
        ),
        "steps": [
            "Open a new Google account (not the one that ran out of free lookups).",
            "Go to Google Cloud and create a new project.",
            "Enable Places API (New) for that project.",
            "Create an API key, copy it, and paste it below.",
        ],
    },
    "geoapify": {
        "signup_url": "https://www.geoapify.com/get-started/",
        "needs_key": True,
        "warning": "",
        "steps": [
            "Create a free Geoapify account.",
            "Open the dashboard and copy your API key.",
            "Paste it below. We will start using it immediately.",
        ],
    },
    "locationiq": {
        "signup_url": "https://locationiq.com/",
        "needs_key": True,
        "warning": "",
        "steps": [
            "Sign up at LocationIQ.",
            "Copy the access token from your dashboard.",
            "Paste it below.",
        ],
    },
    "tomtom": {
        "signup_url": "https://developer.tomtom.com/",
        "needs_key": True,
        "warning": "Use a Search API key, not a Maps SDK-only key.",
        "steps": [
            "Create a TomTom developer account.",
            "Create an API key with Search enabled.",
            "Paste it below.",
        ],
    },
    "yelp": {
        "signup_url": "https://www.yelp.com/developers/v3/manage_app",
        "needs_key": True,
        "warning": "",
        "steps": [
            "Create a Yelp Fusion app.",
            "Copy the API Key (not the Client ID).",
            "Paste it below.",
        ],
    },
    "foursquare": {
        "signup_url": "https://foursquare.com/developers/",
        "needs_key": True,
        "warning": "",
        "steps": [
            "Create a Foursquare developer account.",
            "Create a project and copy the Service / API key.",
            "Paste it below.",
        ],
    },
    "dialcode": {
        "signup_url": "https://dialcode.app/",
        "needs_key": True,
        "warning": "This key is only used to double-check numbers already collected, not to find new ones.",
        "steps": [
            "Create a free DialCode account.",
            "Copy your API key.",
            "Paste it below.",
        ],
    },
    "openstreetmap": {
        "signup_url": "https://www.openstreetmap.org/",
        "needs_key": False,
        "warning": "",
        "steps": [
            "No API key is needed. This public map source is always available.",
        ],
    },
}


def guide_for(slug: str) -> ProviderGuide:
    return GUIDES.get(
        slug,
        {
            "signup_url": "",
            "needs_key": True,
            "warning": "",
            "steps": [
                "Open the provider dashboard, create an API key, and paste it here.",
            ],
        },
    )
