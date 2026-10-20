"""Diverse exploration before refinement, using the existing six-tool boundary.

Descriptors are controller hypotheses, not proof of behavioral diversity. The
source gate catches constant-only/renaming variants; inspected traces and the
independent review are still necessary to assess what actually ran.
"""

import ast
import hashlib
import json

DIMENSIONS = ("grasp_geometry", "motion_geometry", "control_schedule")


def configuration(mode, max_programs):
    if mode == "fix-loop":
        return None
    if mode != "diverse" or max_programs < 5:
        raise ValueError(
            "Diverse search requires at least five programs: four coarse, then refinement"
        )
    return {
        "schema": "so101-diverse-search-v2",
        "coarse_programs": 4,
        "dimensions": list(DIMENSIONS),
        "minimum_changed_dimensions": 2,
        "allow_prerequisite_repair": True,
        "require_budget_exhaustion": False,
        "selection": "maximize assigned physical success, then program_ok; controller chooses among ties from inspected evidence",
    }


def instructions(config):
    legacy = (
        "DIVERSE SEARCH overrides single-correction debugging and AST-size tie-breaking. "
        f"Use the first {config['coarse_programs']} distinct programs for COARSE exploration: "
        "test materially different mechanisms, grasp geometry and control coordination, not tiny changes "
        "of angle/speed/tolerance. The programmer chooses the strategies; no host policy is supplied. "
        "Then use remaining programs to REFINE promising inspected branches, naming their parent. "
        "A large intended maneuver need not mean a larger single control step: choose safe execution "
        "and retain all native guards and success predicates. Do not spend all coarse slots fixing "
        "one family. Common perception and reusable library primitives may be shared. "
        "execute_program.hypothesis MUST be a JSON-encoded object with exactly these fields: "
        "phase ('coarse' or 'refine'), family (short name), dimensions (object with nonempty strings "
        "grasp_geometry, motion_geometry, control_schedule), parent_candidate_id (null for coarse, "
        "an inspected recorded candidate ID for refine), rationale, expected_evidence. "
        "Each coarse family must differ from EVERY earlier coarse family on at least two dimension "
        "descriptions and have different normalized source structure. Labels are hypotheses: explain "
        "concrete source/behavior changes and expected falsifying evidence, not cosmetic renaming. "
        "Inspect results and relevant video frames before every new proposal. Compare requested and "
        "achieved motion, coupling, contact loss and physical predicates; inconclusive vision is unknown. "
        "Do not stop before the program budget is used unless ALL cases meet the assigned physical "
        "criterion or infrastructure prevents experiments. Selection first maximizes physical success "
        "then program_ok. Among exact ties choose and justify the most informative/promising observed "
        "branch; AST size is not preferred. That choice is experimental judgment, never verification "
        "or promotion. Retain rejected hypotheses and regressions in the final comparison."
    )
    if not config.get("allow_prerequisite_repair"):
        return legacy
    return (
        "DIVERSE SEARCH: explore materially different mechanisms, while repairing prerequisites "
        "when perception, closure or control prevents testing a maneuver. Aim for four distinct "
        "coarse families; this is not a mandatory ordering. phase='diagnose' may repair one "
        "inspected parent's prerequisite without changing its intended mechanism. phase='refine' "
        "may improve an inspected parent at any time. Both consume the same program budget. "
        "Keep useful shared perception and verified skills when applicable. Each coarse family "
        "must differ from other coarse families on at least two dimensions and normalized code. "
        "execute_program.hypothesis is JSON with exactly phase ('coarse','diagnose','refine'), "
        "family, dimensions (grasp_geometry,motion_geometry,control_schedule), parent_candidate_id "
        "(null for coarse; inspected candidate for diagnose/refine), rationale, expected_evidence. "
        "Separate requested mechanism, executed motion and measured object response. A closure "
        "failure means the maneuver was not evaluated. Unknown vision is unknown. Inspect public "
        "stage evidence, errors and frames before revising. You may stop before budget exhaustion "
        "when a reproduced prerequisite failure needs adapter/environment engineering; identify "
        "the evidence and missing capability. Otherwise use the budget for useful corrections. "
        "Selection maximizes physical success then program_ok; AST size is not preferred. "
        "Among ties explain measured stage/contact/coupling evidence. Physical success and "
        "independent skill verification remain separate from experimental preferences."
    )


def structural_digest(code):
    """Ignore constants, local names and comments; preserve operations/control/API calls."""

    class Normalize(ast.NodeTransformer):
        def visit_Constant(self, node):
            return ast.copy_location(ast.Constant(value=None), node)

        def visit_Name(self, node):
            return ast.copy_location(ast.Name(id="name", ctx=node.ctx), node)

        def visit_arg(self, node):
            return ast.arg(arg="arg", annotation=None)

        def visit_FunctionDef(self, node):
            self.generic_visit(node)
            node.name = "function"
            return node

    tree = Normalize().visit(ast.parse(code))
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


def descriptor(config, hypothesis, code, previous, root):
    """Validate a new proposal against immutable earlier submissions before running it."""
    try:
        value = json.loads(hypothesis)
    except (ValueError, TypeError) as exc:
        raise ValueError("Diverse search hypothesis must be a JSON object") from exc
    fields = {
        "phase",
        "family",
        "dimensions",
        "parent_candidate_id",
        "rationale",
        "expected_evidence",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Diverse search hypothesis has missing or unexpected fields")
    for name in ("family", "rationale", "expected_evidence"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise ValueError("Search descriptions must be nonempty strings")
    dimensions = value["dimensions"]
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise ValueError(
            "Search dimensions must describe grasp_geometry, motion_geometry, control_schedule"
        )
    if any(not isinstance(v, str) or not v.strip() for v in dimensions.values()):
        raise ValueError("Search dimension descriptions must be nonempty strings")
    adaptive = config.get("allow_prerequisite_repair", False)
    expected = (
        value["phase"]
        if adaptive
        else ("coarse" if len(previous) < config["coarse_programs"] else "refine")
    )
    if expected not in {"coarse", "diagnose", "refine"} or value["phase"] != expected:
        raise ValueError(
            f"Search phase must be {expected}; complete coarse exploration before refinement"
        )
    signature = structural_digest(code)
    if expected == "coarse":
        if value["parent_candidate_id"] is not None:
            raise ValueError("Coarse proposals must have null parent_candidate_id")
        normalize = lambda text: " ".join(text.lower().split())
        for row in previous:
            prior = row["search_strategy"]
            if adaptive and prior["phase"] != "coarse":
                continue
            if normalize(value["family"]) == normalize(prior["family"]):
                raise ValueError("Coarse search requires a different strategy family")
            changed = sum(
                normalize(dimensions[k]) != normalize(prior["dimensions"][k]) for k in DIMENSIONS
            )
            if changed < config["minimum_changed_dimensions"]:
                raise ValueError("Coarse strategies must change at least two dimensions")
            if signature == prior["structural_sha256"]:
                raise ValueError(
                    "Coarse source only changes constants/names; propose a different structure"
                )
    else:
        parents = {row["candidate_id"] for row in previous}
        parent = value["parent_candidate_id"]
        if not isinstance(parent, str) or parent not in parents:
            raise ValueError("Refinement parent must be a prior candidate")
        from cap_harness.so101 import campaign as c

        directory = root / "candidates" / parent
        if (
            not (directory / "inspected.json").exists()
            or c.read_json(directory / "result.json")["status"] != "recorded"
        ):
            raise ValueError("Refinement parent must have inspected, recorded results")
    return {**value, "structural_sha256": signature}
