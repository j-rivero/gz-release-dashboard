from gz_release_dashboard.deps.relations import parse_relations


def names(relations):
    return [[alternative.name for alternative in entry] for entry in relations]


def test_entries_split_on_commas_and_alternatives_on_bars():
    field = "cmake,\n libogre-1.9-dev,\n libogre-2.2-dev | libogre-next-dev,"
    assert names(parse_relations(field)) == [
        ["cmake"],
        ["libogre-1.9-dev"],
        ["libogre-2.2-dev", "libogre-next-dev"],
    ]


def test_version_constraints_profiles_and_multiarch_qualifiers_are_dropped():
    field = (
        "debhelper (>= 13), libgtest-dev <!nocheck>, "
        "libbullet3.24t64 (>= 3.24+dfsg), python3:any"
    )
    assert names(parse_relations(field)) == [
        ["debhelper"],
        ["libgtest-dev"],
        ["libbullet3.24t64"],
        ["python3"],
    ]


def test_a_negated_architecture_qualifier_excludes_only_that_architecture():
    [[dart]] = parse_relations("libdart6.16-dev [!armhf]")
    assert dart.applies_to("amd64")
    assert dart.applies_to("arm64")
    assert not dart.applies_to("armhf")


def test_a_positive_architecture_qualifier_includes_only_those_architectures():
    [[only]] = parse_relations("libfoo-dev [amd64 arm64]")
    assert only.applies_to("arm64")
    assert not only.applies_to("armhf")


def test_an_unqualified_alternative_applies_everywhere():
    [[plain]] = parse_relations("libbullet-dev")
    assert plain.applies_to("arm64")


def test_substitution_variables_are_not_relations():
    field = "${shlibs:Depends}, ${misc:Depends}, libzenohc"
    assert names(parse_relations(field)) == [["libzenohc"]]
