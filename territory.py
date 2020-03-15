from typing import Iterator, Optional
import config


def all() -> Iterator[str]:
    return __flat_territories(None, config.REGIONS)


def __flat_territories(name: Optional[str],
                       region: Optional[dict]) -> Iterator[str]:
    if name:
        yield name

    if region:
        for subregion in region:
            yield from __flat_territories(subregion, region.get(subregion))


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
