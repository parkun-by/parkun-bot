from typing import Iterator
import config


def all() -> Iterator[str]:
    return __flat_territories(config.MINSK, config.REGIONS)


def __flat_territories(name: str, region: dict) -> Iterator[str]:
    if region:
        for subregion in region:
            return __flat_territories(subregion, region[subregion])
    else:
        yield name


def regions(parent_region: str = None) -> Iterator[str]:
    if parent_region:
        for region in config.REGIONS[parent_region]:
            yield region
    else:
        for region in config.REGIONS:
            yield region


def has_subregions(region: str) -> bool:
    if config.REGIONS.get(region):
        return True
    else:
        return False
