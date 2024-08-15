from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel

from faststream._compat import PYDANTIC_V2
from faststream.specification.asyncapi.v2_6_0.schema.bindings import OperationBinding
from faststream.specification.asyncapi.v2_6_0.schema.tag import Tag
from faststream.specification.asyncapi.v2_6_0.schema.utils import Reference
from faststream.specification.asyncapi.v3_0_0.schema.channels import Channel


class Operation(BaseModel):
    """A class to represent an operation.

    Attributes:
        operationId : ID of the operation
        summary : summary of the operation
        description : description of the operation
        bindings : bindings of the operation
        message : message of the operation
        security : security details of the operation
        tags : tags associated with the operation

    """
    action: Literal["send", "receive"]
    summary: Optional[str] = None
    description: Optional[str] = None

    bindings: Optional[OperationBinding] = None

    messages: List[Reference]
    channel: Union[Channel, Reference]

    security: Optional[Dict[str, List[str]]] = None

    # TODO
    # traits

    tags: Optional[List[Union[Tag, Dict[str, Any]]]] = None

    if PYDANTIC_V2:
        model_config = {"extra": "allow"}

    else:

        class Config:
            extra = "allow"
