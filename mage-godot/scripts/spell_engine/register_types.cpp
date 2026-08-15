#include <Godot/core/class_db.hpp>
#include <Godot/godot.hpp>
#include "scripts/spell_engine/godot_spell_engine.hpp" // Your header file

using namespace godot;

void initialize_module(ModuleInitializationLevel p_level) {
	// MUST be scene level
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
	
	// Register the class so ClassDB.instantiate("GodotSpellEngine") works in GDScript!
	ClassDB::register_class<GodotSpellEngine>();
}

void uninitialize_module(ModuleInitializationLevel p_level) {
	if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) {
		return;
	}
}

extern "C" {
GDExtensionBool GDE_EXPORT jenova_library_init(
	GDExtensionInterfaceGetProcAddress p_get_proc_address,
	const GDExtensionClassLibraryPtr p_library,
	GDExtensionInitialization *r_initialization
) {
	godot::GDExtensionBinding::InitObject init_obj(p_get_proc_address, p_library, r_initialization);

	init_obj.register_initializer(initialize_module);
	init_obj.register_uninitializer(uninitialize_module);
	init_obj.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);

	return init_obj.init();
}
}
