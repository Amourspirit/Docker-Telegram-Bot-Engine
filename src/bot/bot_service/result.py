from __future__ import annotations

from typing import Generic, Iterator, TypeGuard, TypeVar

T = TypeVar("T")
E = TypeVar("E", bound=BaseException | None)
TSuccess = TypeVar("TSuccess")
EFailure = TypeVar("EFailure", bound=BaseException)


class Result(Generic[T, E]):
    """Result type that carries either success data or an error."""

    def __init__(self, data: T, error: E) -> None:
        self.data = data
        self.error = error

    def __bool__(self) -> bool:
        return self.error is None

    def __iter__(self) -> Iterator[T | E]:
        return iter((self.data, self.error))

    def __repr__(self) -> str:
        return f"Result(data={self.data!r}, error={self.error!r})"

    @staticmethod
    def success(data: TSuccess) -> "Result[TSuccess, None]":
        return Result(data, None)

    @staticmethod
    def failure(error: EFailure) -> "Result[None, EFailure]":
        return Result(None, error)

    @staticmethod
    def is_success(obj: "Result[TSuccess, BaseException | None]") -> TypeGuard["Result[TSuccess, None]"]:
        return obj.error is None

    @staticmethod
    def is_failure(obj: "Result[TSuccess, BaseException | None]") -> TypeGuard["Result[None, BaseException]"]:
        return obj.error is not None