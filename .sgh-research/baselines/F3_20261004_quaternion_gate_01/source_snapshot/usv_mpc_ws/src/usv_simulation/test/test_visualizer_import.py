def test_visualizer_module_imports():
    import usv_simulation.visualizer as visualizer

    assert hasattr(visualizer, "USVVisualizer")
    assert hasattr(visualizer, "main")
