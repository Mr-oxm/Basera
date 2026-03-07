"""Central icon access for the UI layer."""

from .assets import app_icon, app_icon_path
from .layers import (
	icon_eye,
	icon_lock,
	icon_mask,
	ico_adjustment,
	ico_chain,
	ico_duplicate,
	ico_eraser,
	ico_filter,
	ico_folder,
	ico_fx,
	ico_grid,
	ico_mask,
	ico_mask_layer,
	ico_move,
	ico_new_layer,
	ico_settings,
	ico_text,
	ico_trash,
)
from .properties import (
	move_align_icons,
	move_transform_icons,
	vector_bool_icon,
	vector_node_icon,
)
from .tool_icons import tool_icon, update_tool_icon_colors

__all__ = [
	"app_icon",
	"app_icon_path",
	"icon_eye",
	"icon_lock",
	"icon_mask",
	"ico_adjustment",
	"ico_chain",
	"ico_duplicate",
	"ico_eraser",
	"ico_filter",
	"ico_folder",
	"ico_fx",
	"ico_grid",
	"ico_mask",
	"ico_mask_layer",
	"ico_move",
	"ico_new_layer",
	"ico_settings",
	"ico_text",
	"ico_trash",
	"move_align_icons",
	"move_transform_icons",
	"tool_icon",
	"update_tool_icon_colors",
	"vector_bool_icon",
	"vector_node_icon",
]
