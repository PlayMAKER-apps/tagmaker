# PlayMAKER schema alignment

The sibling [`playmaker-schema` directory](../../playmaker-schema/README.md)
now defines the agreed TagMAKER → VideoMAKER JSON 0.1 contract. Its JSON Schema
and fixture match TagMAKER's existing export. VideoMAKER has no importer yet;
its implementation should use the contract and add tests for clip boundaries,
null game clocks, VFR timestamp estimates, event relationships, and score
corrections. Future incompatible changes require a new version and fixtures.

WebMAKER Studio uses a separate per-game player-stat CSV. TagMAKER's **Export
WebMAKER** action creates that file using source game/player IDs and only
observed statistics. The generic TagMAKER aggregate CSV is not a Studio import.
