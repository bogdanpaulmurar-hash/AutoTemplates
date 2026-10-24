"""Groups for the picker's grouped view (no Qt, so it can be tested anywhere).

Order of the groups:
1. ``FAVOURITES`` (★) and ``RECENT`` on top, only when no category filter is active.
   Recent is hidden while searching (the search ranking already covers it).
2. One group per folder (``Template.category``; ``""`` = top level of the library).
   Without a search: top level first, then folders alphabetically.
   While searching: the folder holding the best-ranked result comes first.

Inside a group the templates keep the order of ``results`` (the search/sort order),
except ``RECENT``, which is ordered by last use.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autotemplates.core.library import Template, Usage, fold

FAVOURITES = "\x00fav"
RECENT = "\x00recent"


@dataclass
class Group:
    key: str  # FAVOURITES, RECENT or the folder path ("" = top level)
    items: list[Template] = field(default_factory=list)

    @property
    def special(self) -> bool:
        return self.key in (FAVOURITES, RECENT)


def folder_title(key: str) -> str:
    """``Emails/Reply`` → ``Emails › Reply``."""
    return " › ".join(part for part in key.split("/") if part)


def recent(results: list[Template], usage: Usage, count: int) -> list[Template]:
    """The ``count`` most recently used templates among ``results`` (newest first)."""
    if count <= 0:
        return []
    used = [t for t in results if usage.last(t.rel) > 0]
    used.sort(key=lambda t: -usage.last(t.rel))
    return used[:count]


def group_results(results: list[Template], usage: Usage, *, searching: bool = False, filtered: bool = False,
                  recent_count: int = 5, favourites_in_folder: bool = True) -> list[Group]:
    """Split ``results`` (already filtered and sorted) into groups; empty groups are left out.

    ``filtered`` = a category filter (a folder or ★) is active: no special groups then.
    ``favourites_in_folder`` = favourites also stay in their folder group (otherwise only under ★).
    """
    groups: list[Group] = []
    show_special = not filtered
    favs: list[Template] = []
    if show_special:
        favs = [t for t in results if usage.favourite(t.rel)]
        if favs:
            groups.append(Group(FAVOURITES, favs))
        if not searching:
            rec = recent(results, usage, recent_count)
            if rec:
                groups.append(Group(RECENT, rec))

    hide_favs = show_special and favs and not favourites_in_folder
    fav_rels = {t.rel for t in favs} if hide_favs else set()
    folders: dict[str, Group] = {}
    for tpl in results:
        if tpl.rel in fav_rels:
            continue
        group = folders.get(tpl.category)
        if group is None:
            group = folders[tpl.category] = Group(tpl.category)
        group.items.append(tpl)

    folder_groups = list(folders.values())  # insertion order = rank of each folder's best result
    if not searching:
        folder_groups.sort(key=lambda g: (g.key != "", fold(g.key)))
    groups.extend(folder_groups)
    return groups
