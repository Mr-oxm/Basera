
import sys
import os
from dataclasses import dataclass, field
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock Layer classes to simulate Document structure
class LayerType:
    GROUP = "GROUP"
    VECTOR = "VECTOR"
    SHAPE = "SHAPE"
    MASK = "MASK"
    ADJUSTMENT = "ADJUSTMENT"
    FILTER = "FILTER"
    TEXT = "TEXT"

@dataclass
class MockLayer:
    id: str
    name: str
    layer_type: str
    parent_id: Optional[str] = None
    mask: Optional[object] = None
    mask_layers: list[str] = field(default_factory=list)

class MockDocument:
    def __init__(self, layers):
        self.layers = layers

# Re-implement the logic from LayersPanel._build_display_order for testing
def build_display_order(document, collapsed, masks_collapsed=None):
    if masks_collapsed is None:
        masks_collapsed = set()
    layers = list(document.layers)
    children_of = {}
    mask_children_of = {}
    adj_children_of = {}
    
    for layer in layers:
        if layer.parent_id:
            if layer.layer_type == LayerType.MASK:
                mask_children_of.setdefault(layer.parent_id, []).append(layer)
            elif layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER):
                adj_children_of.setdefault(layer.parent_id, []).append(layer)
            else:
                children_of.setdefault(layer.parent_id, []).append(layer)

    def _emit_children(lid, indent, result, is_group, group_collapsed):
        has_masks = lid in mask_children_of
        has_adj = lid in adj_children_of
        has_raster = is_group and lid in children_of
        masks_hidden = lid in masks_collapsed

        if is_group and group_collapsed:
            return

        # Mask children
        if has_masks and not masks_hidden:
            for child in reversed(mask_children_of[lid]):
                result.append((child.name, indent))

        # Separator
        if has_masks and has_adj and not masks_hidden:
            result.append(("__SEP__", indent))

        # Adj/filter children
        if has_adj and not masks_hidden:
            for child in reversed(adj_children_of[lid]):
                result.append((child.name, indent))

        # Raster children (groups)
        if has_raster and not group_collapsed:
            if (has_masks or has_adj) and not masks_hidden:
                result.append(("__SEP__", indent))
            for child in reversed(children_of[lid]):
                result.append((child.name, indent))
                # Recurse: This is the logic I fixed
                child_is_group = child.layer_type == LayerType.GROUP
                child_collapsed = child_is_group and child.id in collapsed
                _emit_children(child.id, indent + 1, result,
                               is_group=child_is_group, group_collapsed=child_collapsed)

    result = []
    for layer in reversed(layers):
        if layer.parent_id is not None:
            continue
        is_group = layer.layer_type == LayerType.GROUP
        result.append((layer.name, 0))
        group_collapsed = is_group and layer.id in collapsed
        _emit_children(layer.id, 1, result, is_group, group_collapsed)
    return result

# Test Simulation
def test_nested_groups():
    # Structure:
    # Group A
    #   - Layer A1
    #   - Group B
    #     - Layer B1
    #     - Layer B2
    
    l_grp_a = MockLayer("g1", "Group A", LayerType.GROUP)
    l_a1 = MockLayer("l1", "Layer A1", LayerType.VECTOR, parent_id="g1")
    l_grp_b = MockLayer("g2", "Group B", LayerType.GROUP, parent_id="g1")
    l_b1 = MockLayer("l2", "Layer B1", LayerType.VECTOR, parent_id="g2")
    l_b2 = MockLayer("l3", "Layer B2", LayerType.VECTOR, parent_id="g2")
    
    # Ordered list as if from Document
    # In Document, layers are usually bottom-to-top order.
    # So: [B2, B1, Group B, A1, Group A] or similar depending on implementation.
    # But for display we iterate reversed(layers) and check parent_id.
    
    all_layers = [l_b2, l_b1, l_grp_b, l_a1, l_grp_a] # bottom to top
    doc = MockDocument(all_layers)
    
    print("Testing nested groups with NO collapsed groups:")
    order = build_display_order(doc, collapsed=set())
    for name, indent in order:
        print(f"{'  ' * indent}{name}")
        
    # Validation
    names = [name for name, _ in order]
    expected = ["Group A", "Group B", "Layer B2", "Layer B1", "Layer A1"]
    # Note: order depends on "reversed(children_of[lid])".
    # children_of populated by appending iterating `layers`.
    # l_b1 added before l_b2?
    # layers = [B2, B1, G2, A1, G1]
    # G2 children: B2 then B1.
    # reversed([B2, B1]) -> B1, B2 ??
    
    # Let's trace carefully:
    # layers loop:
    # B2 -> children_of[G2] = [B2]
    # B1 -> children_of[G2] = [B2, B1]
    # G2 -> children_of[G1] = [G2]
    # A1 -> children_of[G1] = [G2, A1]
    # G1 -> top level
    
    # reversed(layers) -> G1, A1, G2, B1, B2
    # Loop over reversed(layers):
    # 1. G1 (parent=None). Result: [("Group A", 0)]
    #    _emit_children(G1):
    #       reversed(children_of[G1]) -> reversed([G2, A1]) -> A1, G2
    #       1. A1. Result: [..., ("Layer A1", 1)]
    #       2. G2. Result: [..., ("Group B", 1)]
    #          _emit_children(G2):
    #             reversed(children_of[G2]) -> reversed([B2, B1]) -> B1, B2
    #             1. B1. Result: [..., ("Layer B1", 2)]
    #             2. B2. Result: [..., ("Layer B2", 2)]
    
    # So expected order: Group A, Layer A1, Group B, Layer B1, Layer B2.
    # Wait, visual stacking is usually top-to-bottom list corresponds to top-to-bottom rendering.
    # In list: Top item is highest Z-index.
    # If layers list is [Bottom, ..., Top]
    # Then reversed(layers) is [Top, ..., Bottom]
    # So G1 is Top. Correct.
    # Inside G1: A1 is Top, G2 is Bottom?
    # children_of[G1] was [G2, A1] (because we iterated bottom-up).
    # So A1 is top-most child of G1.
    # We want display to be Top-Down.
    # So yes, A1 then G2.
    # Inside G2: B1 is Top, B2 is Bottom.
    # So B1 then B2.
    
    # My simulated expected: Group A, Layer A1, Group B, Layer B1, Layer B2.
    
    assert names == ["Group A", "Layer A1", "Group B", "Layer B1", "Layer B2"]
    print("SUCCESS: Nested groups displayed correctly.")

if __name__ == "__main__":
    try:
        test_nested_groups()
    except AssertionError as e:
        print(f"FAILURE: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
