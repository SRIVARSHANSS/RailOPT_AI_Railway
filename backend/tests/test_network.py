import pytest

from app.services.network import format_time, load_network, parse_time


def test_time_helpers():
    assert parse_time("10:03") == 603
    assert parse_time("") is None
    assert format_time(603) == "10:03"


def test_corridor_loads(net):
    assert set(net.stations) == {"A", "B", "C", "D"}
    assert set(net.trains) == {"T101", "T202", "T303"}
    assert net.trains["T101"].priority == 1


def test_b_c_has_main_and_alternate_line(net):
    between = net.sections_between("B", "C")
    assert [s.section_id for s in between] == ["S_BC", "S_BC_ALT"]
    assert net.primary_section("B", "C").section_id == "S_BC"
    assert net.sections["S_BC"].tracks == 1            # the constrained section
    assert net.graph.number_of_edges("B", "C") == 2


def test_default_route_and_shortest_path(net):
    assert [s.section_id for s in net.route_sections("T202")] == ["S_AB", "S_BC", "S_CD"]
    assert net.shortest_route("A", "D") == ["A", "B", "C", "D"]


def test_bad_data_is_rejected(tmp_path, net):
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "data"
    for name in ["stations.csv", "trains.csv", "schedule.csv"]:
        (tmp_path / name).write_text((src / name).read_text())
    (tmp_path / "sections.csv").write_text(
        "section_id,from_station,to_station,length_km,tracks,min_run_min,min_headway_min,status\n"
        "S_AX,A,X,10,1,5,3,open\n")
    with pytest.raises(ValueError):
        load_network(tmp_path)
