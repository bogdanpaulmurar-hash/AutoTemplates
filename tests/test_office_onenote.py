import pytest

from autotemplates.platform import office

SECTION_XML = ('<one:Section xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote" ID="{S}" name="S">'
               '<one:Page ID="{A}" name="A" pageLevel="1"/><one:Page ID="{N}" name="N" pageLevel="1"/></one:Section>')
NOTEBOOKS_XML = ('<one:Notebooks xmlns:one="http://schemas.microsoft.com/office/onenote/2013/onenote">'
                 '<one:Notebook name="N" ID="{NB}"><one:Section name="S" ID="{S}"/></one:Notebook></one:Notebooks>')


class BrokenApp:
    """pywin32 late binding on installs where [out] methods are unknown."""

    def GetHierarchy(self, *args):
        raise AttributeError("OneNote.Application.GetHierarchy")


class FakeBridge:
    def __init__(self):
        self.calls = []

    def hierarchy(self, start, scope):
        self.calls.append(("hierarchy", start, scope))
        return NOTEBOOKS_XML if scope == office.HS_PAGES and not start else SECTION_XML

    def new_page(self, section):
        self.calls.append(("new_page", section))
        return "{N}"

    def update_page(self, xml):
        self.calls.append(("update_page", "{N}" in xml))

    def update_hierarchy(self, xml):
        self.calls.append(("update_hierarchy", xml))

    def navigate(self, page_id):
        self.calls.append(("navigate", page_id))


@pytest.fixture(autouse=True)
def _reset_backend(monkeypatch):
    monkeypatch.setattr(office, "_onenote_backend", None)


def test_backend_falls_back_to_powershell_when_com_binding_fails(monkeypatch):
    monkeypatch.setattr(office, "_dispatch", lambda prog_id: BrokenApp())
    assert isinstance(office._onenote_api(), office._PowerShellOneNote)
    assert office._onenote_api() is office._onenote_api()  # decided once


def test_backend_falls_back_when_pywin32_is_missing(monkeypatch):
    def missing(prog_id):
        raise office.OfficeUnavailable("pywin32 is not installed")

    monkeypatch.setattr(office, "_dispatch", missing)
    assert isinstance(office._onenote_api(), office._PowerShellOneNote)


def test_sections_and_subpage_use_the_bridge(monkeypatch):
    bridge = FakeBridge()
    monkeypatch.setattr(office, "_onenote_backend", bridge)
    assert [s.id for s in office.onenote_sections()] == ["{S}"]
    office.create_onenote_page("{S}", "T", "<p>x</p>", parent_page_id="{A}")
    names = [c[0] for c in bridge.calls]
    assert names[-4:] == ["new_page", "update_page", "hierarchy", "update_hierarchy"] or names[-5:] == [
        "new_page", "update_page", "hierarchy", "update_hierarchy", "navigate"]
    assert ("navigate", "{N}") in bridge.calls


def test_error_message_names_the_exception_type(monkeypatch):
    class Boom(FakeBridge):
        def hierarchy(self, start, scope):
            raise AttributeError("OneNote.Application.GetHierarchy")

    monkeypatch.setattr(office, "_onenote_backend", Boom())
    with pytest.raises(office.OfficeUnavailable, match="AttributeError"):
        office.onenote_sections()
