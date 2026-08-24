"""Backward-compatible alias: `import zh_graphql_ops` → `zh.graphql_ops`."""

import sys

import zh.graphql_ops

sys.modules[__name__] = zh.graphql_ops
