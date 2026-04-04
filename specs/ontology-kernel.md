# Ontology Kernel & Templates

RAIL ontologies are structured in three layers: an immutable kernel, a composable standard library of templates, and fully custom project extensions. This document specifies all three layers.

---

## Layer 1 — The Kernel

The kernel is a minimal set of OWL data properties that are automatically present on **every individual in every project ontology**, regardless of domain. It is defined in `packages/engine/ontology/kernel.yaml` and is never edited. Changing a kernel property is a breaking change to the entire platform.

### Kernel Properties

| Property | Range | Functional | Purpose |
|----------|-------|------------|---------|
| `hasName` | str | yes | Human-readable label for the individual |
| `hasSource` | str | yes | Name of the data source config that produced this individual (matches API config `name` field) |
| `hasSourceURL` | str | yes | Provenance URL — the actual endpoint or file path data came from |
| `hasIngestDate` | str | yes | ISO 8601 date string of the hydration run that created this individual |
| `hasPipelineID` | str | yes | Unique identifier of the hydration job run |
| `hasCreatedAt` | str | yes | ISO 8601 timestamp of individual creation within the run |

### Kernel YAML (`packages/engine/ontology/kernel.yaml`)

```yaml
uri: http://rail.rutgers.edu/ontology/kernel
data_properties:
  - name: hasName
    domain: [Thing]
    range: str
    functional: true
  - name: hasSource
    domain: [Thing]
    range: str
    functional: true
  - name: hasSourceURL
    domain: [Thing]
    range: str
    functional: true
  - name: hasIngestDate
    domain: [Thing]
    range: str
    functional: true
  - name: hasPipelineID
    domain: [Thing]
    range: str
    functional: true
  - name: hasCreatedAt
    domain: [Thing]
    range: str
    functional: true
```

### How the Kernel is Applied

The hydration worker prepends the kernel module to the ontology config before writing to the tmpdir. Projects never declare kernel properties in their own YAML — they are always present.

```python
# hydration_worker.py (pseudocode)
kernel_yaml = read("packages/engine/ontology/kernel.yaml")
project_ontology_yaml = fetch_from_convex(ontology_slug)
merged = merge_ontology_yamls(kernel_yaml, project_ontology_yaml)
write_to_tmpdir("configs/ontology/merged.yaml", merged)
```

Merge rule: the kernel's `data_properties` list is prepended to the project's `data_properties` list. The project's `uri` and `classes` are unchanged. If a project accidentally declares a property with the same name as a kernel property, the kernel definition takes precedence and a warning is logged.

---

## Layer 2 — Ontology Templates (Standard Library)

Templates are reusable ontology modules stored in the Convex `ontologyTemplates` table. Any platform user can create, edit, or fork a template. Templates are **additive** — they only add classes and properties, never remove or constrain. The open-world assumption in OWL means applying a template never restricts what a project can do.

### Template Structure

Each template is a YAML document with the same structure as a project ontology config, plus metadata fields:

```yaml
# Template stored in Convex ontologyTemplates table
name: US Geography
slug: us-geography
description: "US geographic hierarchy: State, County, Municipality, ZipCode, CensusTract"
version: "1.0"
tags: [geography, us, census]
content: |
  uri: http://rail.rutgers.edu/ontology/us-geography
  classes:
    - name: GeographicRegion
      parent: Thing
    - name: Nation
      parent: GeographicRegion
    - name: State
      parent: GeographicRegion
    - name: County
      parent: GeographicRegion
    - name: Municipality
      parent: GeographicRegion
    - name: ZipCode
      parent: GeographicRegion
    - name: CensusTract
      parent: GeographicRegion
  object_properties:
    - name: isPartOf
      domain: [GeographicRegion]
      range: [GeographicRegion]
      inverse: hasPart
    - name: locatedIn
      domain: [Thing]
      range: [GeographicRegion]
  data_properties:
    - name: hasFIPS
      domain: [GeographicRegion]
      range: str
      functional: true
    - name: hasAbbreviation
      domain: [GeographicRegion]
      range: str
      functional: true
    - name: hasISO2
      domain: [GeographicRegion]
      range: str
      functional: true
    - name: hasISO3
      domain: [GeographicRegion]
      range: str
      functional: true
    - name: hasRegionCode
      domain: [GeographicRegion]
      range: str
      functional: true
    - name: hasPopulation
      domain: [GeographicRegion]
      range: int
      functional: true
```

### Available Templates

| Slug | Classes | Use for |
|------|---------|---------|
| `us-geography` | GeographicRegion, Nation, State, County, Municipality, ZipCode, CensusTract | Any US geographic data |
| `economic-indicators` | Observation, Measure, LaborIndicator, HousingIndicator, IncomeIndicator, MacroIndicator, EnvironmentIndicator, DataSeries | Economic time series |
| `demographics` | DemographicIndicator, EducationIndicator, Individual | Population and person-level data |
| `platform-objects` | DataSource, Pipeline, OntologyModule, AnalysisScript, Agent, Project, HydrationJob, ArtifactFile | Platform self-description (applied to all projects automatically) |

The `platform-objects` template is automatically applied to every project ontology. It is what makes datasets, pipelines, agents, and scripts first-class individuals in the knowledge graph — queryable through the same DuckDB/SPARQL surface as domain data.

### Applying Templates at Project Creation

When a project is created, selected template YAML modules are merged into the project's initial `ontology.yaml`. After creation, the project owns its ontology YAML — templates are not re-applied on subsequent hydrations unless the project's YAML explicitly imports them.

Merge order: `kernel` → `platform-objects` → selected templates (in order) → project extension. Later entries in the merge override earlier entries only for `uri`; `classes`, `object_properties`, and `data_properties` lists are concatenated and deduplicated by `name`.

### Convex Schema — `ontologyTemplates`

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | Display name |
| `slug` | string | Unique identifier (indexed `by_slug`) |
| `description` | string | What this module models |
| `version` | string | Semver string |
| `tags` | string[] | For filtering in the UI |
| `content` | string | Raw YAML of the ontology module |
| `createdBy` | string | User identifier |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

---

## Layer 3 — Project Extensions (Userspace)

The project's own ontology YAML is unconstrained. Any classes, any properties, any relationships. There are only three rules:

1. **Never redefine kernel properties.** If a project declares a property with the same name as a kernel property, the kernel definition wins at hydration time.
2. **Class names must be unique within a project.** Two classes with the same name in the same ontology is an error.
3. **Object property domains and ranges must reference classes that exist in the merged ontology** (kernel + templates + project extension). Forward references within the same file are allowed (the engine processes all classes before all properties).

Everything else is up to the project. Domain teams define whatever classes and relationships model their data best.

### Example: Economic Research Project

A project studying New Jersey labor markets might define:

```yaml
uri: http://rail.rutgers.edu/ontology/nj-economics
# Templates applied at creation: us-geography, economic-indicators
# Kernel applied automatically at hydration

# Project-specific extension:
classes:
  - name: MetroArea
    parent: GeographicRegion    # extends from us-geography template

object_properties:
  - name: includesCounty
    domain: [MetroArea]
    range: [County]             # County defined in us-geography template

data_properties:
  - name: hasMetroCode
    domain: [MetroArea]
    range: str
    functional: true
  - name: hasLaborForceSize
    domain: [State, County, MetroArea]
    range: int
    functional: true
```

At hydration, the engine sees: kernel properties + platform-objects classes + us-geography classes/properties + economic-indicators classes/properties + project extension. The result is a single merged OWL ontology.

### Example: Climate Research Project (Different Domain)

```yaml
uri: http://rail.rutgers.edu/ontology/nj-climate
# Templates applied at creation: us-geography
# (economic-indicators not selected — no overlap with this domain)

classes:
  - name: WeatherStation
    parent: Thing
  - name: AirQualityReading
    parent: Thing
  - name: TemperatureReading
    parent: Thing

object_properties:
  - name: stationLocatedIn
    domain: [WeatherStation]
    range: [State, County]      # reuses geography from template

data_properties:
  - name: hasStationID
    domain: [WeatherStation]
    range: str
    functional: true
  - name: hasPM25
    domain: [AirQualityReading]
    range: float
    functional: true
  - name: hasOzoneLevel
    domain: [AirQualityReading]
    range: float
    functional: true
  - name: hasTemperatureCelsius
    domain: [TemperatureReading]
    range: float
    functional: true
  - name: hasReadingDate
    domain: [AirQualityReading, TemperatureReading]
    range: str
    functional: true
```

The kernel and `platform-objects` are always present. The `us-geography` template gives the project geography for free. Everything else is domain-specific and defined here.

---

## Platform Objects — Self-Describing Ontology

The `platform-objects` template (always applied) makes the platform itself part of the knowledge graph. This enables agents to query what exists, trace provenance, and reason about the system.

### Platform Classes and Key Properties

**`DataSource`** — a configured data connector instance
- `hasName`, `hasSlug` (str), `hasConnectorTemplate` (str, slug of parent template), `hasProjectSlug` (str)

**`Pipeline`** — an ordered hydration workflow
- `hasName`, `hasSlug`, `hasProjectSlug`, `hasInputDataSources` (non-functional, str list of api config slugs), `hasOutputClasses` (non-functional, str list of OWL class names)

**`OntologyModule`** — an ontology YAML definition
- `hasName`, `hasSlug`, `hasProjectSlug`, `hasURI` (str, the OWL ontology IRI)

**`AnalysisScript`** — a Python analysis plugin
- `hasName`, `hasSlug`, `hasProjectSlug`, `hasInputClasses` (non-functional), `hasDescription` (str)

**`Agent`** — a domain agent configuration
- `hasName`, `hasProjectSlug`, `hasModel` (str), `hasAllowedActions` (non-functional, str list)

**`Project`** — a research domain
- `hasName`, `hasSlug`, `hasGitHubRepo` (str), `hasStatus` (str: draft/ready/hydrated)

**`HydrationJob`** — a concrete pipeline run
- `hasName` (pipeline slug + run ID), `hasStatus` (str), `hasPipelineSlug` (str), `hasStartedAt`, `hasFinishedAt`

**`ArtifactFile`** — output from a run (CSV, model, figure)
- `hasName`, `hasStorageKey` (str), `hasJobID` (str), `hasMimeType` (str)

These individuals are written into the ontology by the hydration worker on each run, using the kernel properties (`hasPipelineID`, `hasIngestDate`, etc.) for provenance. This means every DuckDB export includes a `Pipeline`, `DataSource`, `OntologyModule`, etc. table that the agent can query directly.

---

## IRI Conventions

All individuals use the project's ontology URI as the namespace:

```
http://rail.rutgers.edu/ontology/{project-slug}#{ClassName}_{local-id}
```

Examples:
```
http://rail.rutgers.edu/ontology/nj-economics#State_34
http://rail.rutgers.edu/ontology/nj-economics#LaborIndicator_NJURN_2024-01-01
http://rail.rutgers.edu/ontology/nj-economics#Pipeline_nj-hydration
```

The local ID is derived from the pipeline YAML's `uri` template and sanitized (non-`[A-Za-z0-9_\-.]` characters replaced with `_`).

Platform object individuals follow:
```
http://rail.rutgers.edu/ontology/{project-slug}#Pipeline_{pipeline-slug}
http://rail.rutgers.edu/ontology/{project-slug}#DataSource_{api-config-slug}
```
