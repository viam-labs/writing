from typing import ClassVar, Mapping, Optional, Sequence, Tuple

from typing_extensions import Self
from viam.components.arm import Arm
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import ResourceName
from viam.resource.base import ResourceBase
from viam.resource.easy_resource import EasyResource
from viam.resource.types import Model, ModelFamily
from viam.services.generic import *
from viam.utils import ValueTypes


class WriterCoordinator(Generic, EasyResource):
    # To enable debug-level logging, either run viam-server with the --debug option,
    # or configure your resource/machine to display debug logs.
    MODEL: ClassVar[Model] = Model(
        ModelFamily("chess-piece-detection", "writer"), "writer-coordinator"
    )

    arm: Arm

    @classmethod
    def new(
        cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]
    ) -> Self:
        service = super().new(config, dependencies)
        arm_name = config.attributes.fields["arm"].string_value
        service.arm = dependencies[Arm.get_resource_name(arm_name)]
        return service

    @classmethod
    def validate_config(
        cls, config: ComponentConfig
    ) -> Tuple[Sequence[str], Sequence[str]]:
        arm_name = config.attributes.fields["arm"].string_value
        if not arm_name:
            raise ValueError('"arm" is required')
        return [arm_name], []

    async def do_command(
        self,
        command: Mapping[str, ValueTypes],
        *,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Mapping[str, ValueTypes]:
        self.logger.error("`do_command` is not implemented")
        raise NotImplementedError()

    async def get_status(
        self, *, timeout: Optional[float] = None, **kwargs
    ) -> Mapping[str, ValueTypes]:
        self.logger.error("`get_status` is not implemented")
        raise NotImplementedError()
