
__pragma__('alias', 'S', '$')  # to use jQuery library with 'S' instead of '$'


def get_element(css_selectors):
    return document.querySelector(css_selectors)


def get_Element(css_selectors):
    return ElementWrapper(get_element(css_selectors))


def get_elements(css_selectors):
    return document.querySelectorAll(css_selectors)


def element(name):
    return document.createElement(name)


def Element(name):
    return ElementWrapper(element(name))


class ElementWrapper():
    def __init__(self, element):
        if element == None:
            raise Exception("ElementWrapper: element cannot be None")
        self.element = element

    def append(self, *others):
        for o in others:
            self.element.appendChild(o.element)
        return self

    def attr(self, name, value):
        if value is None:
            self.element.setAttributeNode(document.createAttribute(name))
        else:
            self.element.setAttribute(name, value)
        return self

    def remove_attr(self, name):
        self.element.removeAttribute(name)
        return self

    def enable(self, enable=True):
        if enable:
            return self.remove_attr("disabled")
        else:
            return self.disable()

    def disable(self):
        return self.attr('disabled', None)

    def is_enabled(self):
        return not self.element.hasAttribute("disabled")

    def remove_childs(self):
        while self.element.hasChildNodes():
            self.element.removeChild(self.element.firstChild)

    def remove_from_parent(self):
        self.element.parentNode.removeChild(self.element)

    def children(self):
        return Array.prototype.slice.call(self.element.children)

    def index_in_parent(self):
        return self.children().indexOf(self.element)

    def insert_before(self, newnode: 'ElementWrapper', existingnode: 'ElementWrapper'):
        return self.element.insertBefore(newnode.element, existingnode.element)

    def inner_html(self, txt):
        self.element.innerHTML = txt
        return self

    def text(self, txt):
        self.element.textContent = txt
        return self
