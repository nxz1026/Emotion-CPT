"""契约层的异常类型。"""

from __future__ import annotations


class ContractError(RuntimeError):
    """契约本身自相矛盾（如同一张表被登记成两个归属）。"""


class ContractDriftError(ContractError):
    """本仓契约与实际（代码 / 真库）不一致。"""
