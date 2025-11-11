import abc
from pydantic import BaseModel
from typing import Union, TypeVar, Type, Any, Dict

A = TypeVar('A', bound="PydanticDataClassJsonMixin")


class PydanticDataClassJsonMixin(abc.ABC):

    @classmethod
    def _validate_cls(cls):
        if not issubclass(cls, BaseModel):
            raise TypeError(
                f"Class {cls.__name__} must be a subclass of BaseModel"
            )

    def to_json(self: BaseModel) -> str:
        self._validate_cls()
        return self.model_dump_json()

    def to_dict(self: BaseModel) -> Dict[str, Any]:
        self._validate_cls()
        return self.model_dump()

    @classmethod
    def from_json(cls: Type[A], json_data: Union[str, bytes, bytearray]) -> A:
        cls._validate_cls()
        return cls.model_validate_json(json_data)

    @classmethod
    def from_dict(cls: Type[A], dict_data: Any) -> A:
        cls._validate_cls()
        return cls.model_validate(dict_data)


def pydantic_dataclass_json(_cls=None):
    """
    Based on the code in the `dataclasses` module to handle optional-parens
    decorators. See example below:

    @dataclass_json
    class Example:
        ...
    """

    def wrap(cls):
        cls.to_json = PydanticDataClassJsonMixin.to_json
        cls._validate_cls = classmethod(PydanticDataClassJsonMixin._validate_cls.__func__)  # type: ignore
        cls.from_json = classmethod(PydanticDataClassJsonMixin.from_json.__func__)  # type: ignore
        cls.to_dict = PydanticDataClassJsonMixin.to_dict
        cls.from_dict = classmethod(PydanticDataClassJsonMixin.from_dict.__func__)  # type: ignore

        PydanticDataClassJsonMixin.register(cls)
        return cls

    if _cls is None:
        return wrap
    return wrap(_cls)
