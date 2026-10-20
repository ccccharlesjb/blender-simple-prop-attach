bl_info = {
    "name": "Simple Prop Attach",
    "author": "ccccharlesjb (AI-generated)",
    "version": (1, 8, 0),
    "blender": (5, 2, 0),
    "location": "View3D > N-Panel > Rigging",
    "description": "Automates weight transfer for flexible clothing and rigid props in Blender 5.2.",
    "category": "Rigging",
}

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def sample_body_weights_at_location(body_mesh, world_loc, context):
    """
    Samples vertex group weights from the nearest surface point on the body mesh.
    Returns a dictionary of {vertex_group_name: weight_value}.
    """
    depsgraph = context.evaluated_depsgraph_get()
    body_eval = body_mesh.evaluated_get(depsgraph)
    mesh_data = body_eval.data

    bvh = BVHTree.FromObject(body_mesh, depsgraph)
    local_loc = body_mesh.matrix_world.inverted() @ world_loc
    hit_loc, norm, face_idx, dist = bvh.find_nearest(local_loc)

    if face_idx is None:
        return {}

    poly = mesh_data.polygons[face_idx]
    
    weight_sums = {}
    total_inverse_dist = 0.0

    for v_idx in poly.vertices:
        vert = mesh_data.vertices[v_idx]
        d = (vert.co - hit_loc).length
        inv_d = 1.0 / max(d, 0.00001)
        total_inverse_dist += inv_d

        for g in vert.groups:
            if g.group < len(body_eval.vertex_groups):
                vg_name = body_eval.vertex_groups[g.group].name
                weight_sums[vg_name] = weight_sums.get(vg_name, 0.0) + (g.weight * inv_d)

    if total_inverse_dist <= 0:
        return {}

    final_weights = {}
    for vg_name, w_sum in weight_sums.items():
        avg_w = w_sum / total_inverse_dist
        if avg_w > 0.001:
            final_weights[vg_name] = avg_w

    total_w = sum(final_weights.values())
    if total_w > 0:
        final_weights = {k: v / total_w for k, v in final_weights.items()}

    return final_weights


def create_or_update_socket_bone(target_armature, obj_name, world_loc, sampled_weights, context):
    """
    Creates a dedicated socket bone at the accessory's initial location.
    Uses Child Of constraints with rest inverse matrices so initial transform is 100% preserved.
    """
    socket_bone_name = f"socket_{obj_name}"
    orig_active = context.view_layer.objects.active
    
    context.view_layer.objects.active = target_armature
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    arm_data = target_armature.data
    dominant_bone = max(sampled_weights, key=sampled_weights.get)

    bpy.ops.object.mode_set(mode='EDIT')
    
    if socket_bone_name in arm_data.edit_bones:
        eb = arm_data.edit_bones[socket_bone_name]
    else:
        eb = arm_data.edit_bones.new(socket_bone_name)

    local_head = target_armature.matrix_world.inverted() @ world_loc
    eb.head = local_head
    eb.tail = local_head + Vector((0, 0, 0.1))
    eb.use_connect = False

    if len(sampled_weights) == 1 and dominant_bone in arm_data.edit_bones:
        eb.parent = arm_data.edit_bones[dominant_bone]
    else:
        eb.parent = None

    bpy.ops.object.mode_set(mode='OBJECT')

    if len(sampled_weights) > 1:
        pbone = target_armature.pose.bones.get(socket_bone_name)
        if pbone:
            for const in list(pbone.constraints):
                pbone.constraints.remove(const)

            for bone_name, weight in sampled_weights.items():
                if bone_name in arm_data.bones:
                    c = pbone.constraints.new(type='CHILD_OF')
                    c.target = target_armature
                    c.subtarget = bone_name
                    c.influence = weight
                    
                    c.use_scale_x = False
                    c.use_scale_y = False
                    c.use_scale_z = False

                    rest_matrix = arm_data.bones[bone_name].matrix_local
                    c.inverse_matrix = rest_matrix.inverted()

    context.view_layer.objects.active = orig_active
    return socket_bone_name


def process_accessory_smooth(obj, target_armature, body_mesh, context):
    """Data Transfer method for flexible items (clothing, hair, soft straps)."""
    world_matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world_matrix

    obj.vertex_groups.clear()

    obj.parent = target_armature
    obj.matrix_world = world_matrix

    arm_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
    if not arm_mod:
        arm_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    arm_mod.object = target_armature

    dt_mod = obj.modifiers.new(name="DataTransfer_Temp", type='DATA_TRANSFER')

    with context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.modifier_move_to_index(modifier=dt_mod.name, index=0)

    dt_mod.object = body_mesh
    dt_mod.use_vert_data = True
    dt_mod.data_types_verts = {'VGROUP_WEIGHTS'}
    dt_mod.vert_mapping = 'POLYINTERP_NEAREST'

    with context.temp_override(object=obj, active_object=obj):
        bpy.ops.object.datalayout_transfer(modifier=dt_mod.name)
        bpy.ops.object.modifier_apply(modifier=dt_mod.name)


def process_accessory_rigid(obj, target_armature, body_mesh, context, rigid_type):
    """Rigid Attachment method for hard items (pouches, holsters, armor plates)."""
    world_matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world_matrix

    obj.vertex_groups.clear()

    bbox_verts = [world_matrix @ Vector(corner) for corner in obj.bound_box]
    center_world = sum(bbox_verts, Vector()) / len(bbox_verts)

    sampled_weights = sample_body_weights_at_location(body_mesh, center_world, context)

    if not sampled_weights:
        raise RuntimeError(f"Could not sample surface weights near '{obj.name}'.")

    all_vert_indices = list(range(len(obj.data.vertices)))

    if rigid_type == 'DOMINANT':
        dominant_bone = max(sampled_weights, key=sampled_weights.get)
        vg = obj.vertex_groups.new(name=dominant_bone)
        vg.add(all_vert_indices, 1.0, 'REPLACE')

    elif rigid_type == 'MULTI':
        for vg_name, weight in sampled_weights.items():
            vg = obj.vertex_groups.new(name=vg_name)
            vg.add(all_vert_indices, weight, 'REPLACE')

    elif rigid_type == 'SOCKET':
        socket_bone_name = create_or_update_socket_bone(
            target_armature, obj.name, center_world, sampled_weights, context
        )
        vg = obj.vertex_groups.new(name=socket_bone_name)
        vg.add(all_vert_indices, 1.0, 'REPLACE')

    obj.parent = target_armature
    obj.matrix_world = world_matrix

    arm_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
    if not arm_mod:
        arm_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
    arm_mod.object = target_armature


class OBJECT_OT_auto_weight_transfer(bpy.types.Operator):
    """Parent selected accessories to rig and transfer/conform weights"""
    bl_idname = "object.auto_weight_transfer"
    bl_label = "Conform & Attach to Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        target_armature = scene.auto_weight_armature
        target_body = scene.auto_weight_body
        mode = scene.auto_weight_mode
        rigid_type = scene.auto_weight_rigid_type

        if not target_armature:
            self.report({'ERROR'}, "Target Armature is not selected.")
            return {'CANCELLED'}

        if not target_body:
            self.report({'ERROR'}, "Source Body Mesh is not selected.")
            return {'CANCELLED'}

        if len(target_body.vertex_groups) == 0:
            self.report({'WARNING'}, f"Body Mesh '{target_body.name}' has no vertex groups.")

        selected_objs = [
            obj for obj in context.selected_objects 
            if obj.type == 'MESH' and obj != target_body
        ]

        if not selected_objs:
            self.report({'ERROR'}, "Select at least one accessory mesh object.")
            return {'CANCELLED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        success_count = 0
        failed_objs = []

        for obj in selected_objs:
            try:
                if obj.library or (obj.data and obj.data.library):
                    raise RuntimeError(f"'{obj.name}' is linked from an external file.")

                if mode == 'SMOOTH' and obj.data.shape_keys and len(obj.data.shape_keys.key_blocks) > 0:
                    raise RuntimeError(f"'{obj.name}' has Shape Keys (cannot apply Data Transfer).")

                if obj.data.users > 1:
                    obj.data = obj.data.copy()

                context.view_layer.objects.active = obj

                if mode == 'SMOOTH':
                    process_accessory_smooth(obj, target_armature, target_body, context)
                elif mode == 'RIGID':
                    process_accessory_rigid(obj, target_armature, target_body, context, rigid_type)

                success_count += 1

            except Exception as err:
                failed_objs.append((obj.name, str(err)))

        if failed_objs:
            for name, reason in failed_objs:
                self.report({'ERROR'}, f"Failed on '{name}': {reason}")
            if success_count > 0:
                self.report({'WARNING'}, f"Processed {success_count} object(s), but {len(failed_objs)} failed.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Successfully conformed {success_count} object(s).")
        return {'FINISHED'}


class VIEW3D_PT_auto_weight_panel(bpy.types.Panel):
    bl_label = "Simple Prop Attach"
    bl_idname = "VIEW3D_PT_auto_weight_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Rigging'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        box = layout.box()
        box.label(text="Target Configuration", icon='ARMATURE_DATA')
        box.prop(scene, "auto_weight_armature", text="Target Rig")
        box.prop(scene, "auto_weight_body", text="Body Mesh")

        box_mode = layout.box()
        box_mode.label(text="Attachment Mode", icon='MODIFIER')
        box_mode.prop(scene, "auto_weight_mode", expand=True)

        if scene.auto_weight_mode == 'RIGID':
            box_rigid = box_mode.box()
            box_rigid.label(text="Rigid Strategy:", icon='BONE_DATA')
            box_rigid.prop(scene, "auto_weight_rigid_type", text="")

        layout.separator()
        layout.operator("object.auto_weight_transfer", icon='MOD_DATA_TRANSFER')


def register():
    bpy.utils.register_class(OBJECT_OT_auto_weight_transfer)
    bpy.utils.register_class(VIEW3D_PT_auto_weight_panel)

    bpy.types.Scene.auto_weight_armature = bpy.props.PointerProperty(
        name="Target Rig",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'ARMATURE'
    )
    bpy.types.Scene.auto_weight_body = bpy.props.PointerProperty(
        name="Source Body Mesh",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )
    bpy.types.Scene.auto_weight_mode = bpy.props.EnumProperty(
        name="Mode",
        description="Choose how weights are applied to selected items",
        items=[
            ('SMOOTH', "Smooth Deform", "Data Transfer for deforming items like clothing, cape, soft boots."),
            ('RIGID', "Rigid Attachment", "Weighting for hard items like belt pouches, holsters, armor plates."),
        ],
        default='SMOOTH'
    )
    bpy.types.Scene.auto_weight_rigid_type = bpy.props.EnumProperty(
        name="Rigid Strategy",
        description="Select weighting method for rigid objects",
        items=[
            ('SOCKET', "Create Socket Bone", "Generates a socket bone in the rig and weights 100% of the mesh to it. Prevents shrinking and floating."),
            ('DOMINANT', "Weight to Dominant Bone", "Paints 100% weight to the single nearest bone. Creates no new bones."),
            ('MULTI', "Weight to Surface Blend", "Paints uniform multi-bone surface weights across all vertices. Creates no new bones."),
        ],
        default='SOCKET'
    )


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_auto_weight_panel)
    bpy.utils.unregister_class(OBJECT_OT_auto_weight_transfer)

    del bpy.types.Scene.auto_weight_armature
    del bpy.types.Scene.auto_weight_body
    del bpy.types.Scene.auto_weight_mode
    del bpy.types.Scene.auto_weight_rigid_type


if __name__ == "__main__":
    register()