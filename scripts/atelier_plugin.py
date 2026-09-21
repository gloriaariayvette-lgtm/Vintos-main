#!/usr/bin/env python3
"""Atelier-facing plugin access and receipt retrieval."""
from plugin_gateway import call, load_receipt


def query(plugin, tool, arguments, purpose):
    return call("atelier", plugin, tool, arguments, purpose)


def artifact(receipt_id):
    return load_receipt(receipt_id, "atelier")
