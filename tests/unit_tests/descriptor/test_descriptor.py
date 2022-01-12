import pytest

from zntrack.descriptor.descriptor import Descriptor, Metadata


def test_metadata():
    metadata = Metadata(dvc_option="plots_no_cache", zntrack_type="zn")
    assert metadata.dvc_args == "plots-no-cache"


@pytest.fixture
def example_class():
    class ExampleDescriptor(Descriptor):
        metadata = Metadata(dvc_option="dvc_option", zntrack_type="zntrack_type")

    class Mock:
        entry = ExampleDescriptor()
        entry_w_default = ExampleDescriptor("Lorem Ipsum")

    return Mock()


def test_descriptor__get(example_class):
    assert example_class.entry is None
    assert example_class.entry_w_default == "Lorem Ipsum"


def test_descriptor__set(example_class):
    example_class.entry = "entry"
    example_class.entry_w_default = "entry_w_default"
    assert example_class.__dict__["entry"] == "entry"
    assert example_class.__dict__["entry_w_default"] == "entry_w_default"


@pytest.fixture
def example_class_w_get_set():
    class ExampleDescriptor(Descriptor):
        metadata = Metadata(dvc_option="dvc_option", zntrack_type="zntrack_type")

        def set(self, instance, value):
            instance.__dict__[self.name] = f"{value}_post"

        def get(self, instance, owner):
            return f"pre_{instance.__dict__[self.name]}"

    class Mock:
        entry = ExampleDescriptor()
        entry_w_default = ExampleDescriptor("Lorem Ipsum")

    return Mock()


def test_descriptor_get(example_class_w_get_set):
    with pytest.raises(KeyError):
        assert example_class_w_get_set.entry is None
        assert example_class_w_get_set.entry_w_default == "pre_Lorem Ipsum"

    example_class_w_get_set.entry = "test"

    assert example_class_w_get_set.entry == "pre_test_post"


def test_descriptor_set(example_class_w_get_set):
    example_class_w_get_set.entry = "entry"
    example_class_w_get_set.entry_w_default = "entry_w_default"
    assert example_class_w_get_set.__dict__["entry"] == "entry_post"
    assert example_class_w_get_set.__dict__["entry_w_default"] == "entry_w_default_post"
