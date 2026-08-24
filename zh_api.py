"""Backward-compatible alias: `import zh_api` → `zh.api`."""

import sys

import zh.api

sys.modules[__name__] = zh.api
