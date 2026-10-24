import asyncio

from viam.module.module import Module

# Imported for its side effect: EasyResource registers the model on import.
from models.writer_coordinator import WriterCoordinator  # noqa: F401

if __name__ == "__main__":
    asyncio.run(Module.run_from_registry())
