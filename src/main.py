import asyncio
from viam.module.module import Module
from models.writer_coordinator import WriterCoordinator as WriterCoordinatorModel


if __name__ == '__main__':
    asyncio.run(Module.run_from_registry())
