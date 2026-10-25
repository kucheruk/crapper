"""C# source complexity; member signatures keep overloads distinct.

Local functions and lambdas belong to their enclosing member. Auto-properties
and abstract declarations have no executable body and are omitted.
"""

from crapper.languages.treesitter import (
    child_of_type, complexity, descendants, end_line, node_text, parse, start_line,
)
from crapper.model import Function

_TYPES = {'class_declaration', 'struct_declaration', 'interface_declaration', 'record_declaration'}
_MEMBERS = {'method_declaration', 'constructor_declaration', 'destructor_declaration',
            'operator_declaration', 'conversion_operator_declaration', 'accessor_declaration'}
_DECISIONS = {'if_statement', 'for_statement', 'foreach_statement', 'while_statement',
              'do_statement', 'catch_clause', 'conditional_expression', 'switch_section',
              'switch_expression_arm', 'conditional_access_expression', 'when_clause',
              'and_pattern', 'or_pattern'}


def _decision(node):
    return node.type in _DECISIONS or (
        node.type == 'binary_expression' and any(c.type in {'&&', '||', '??'} for c in node.children)
    )


def _name(data, node):
    ident = node.child_by_field_name('name')
    return node_text(data, ident) if ident is not None else ''


def _type_name(data, node):
    parameters = child_of_type(node, 'type_parameter_list')
    return _name(data, node) + (node_text(data, parameters) if parameters is not None else '')


def _namespace(data, node, root):
    parts = []
    current = node.parent
    while current is not None:
        if current.type in _TYPES:
            parts.append(_type_name(data, current))
        elif current.type == 'namespace_declaration':
            parts.append(_name(data, current))
        current = current.parent
    scoped = child_of_type(root, 'file_scoped_namespace_declaration')
    if scoped is not None:
        parts.append(_name(data, scoped))
    return '.'.join(reversed(parts)) or 'Program'


def _parameters(data, node):
    parameters = child_of_type(node, 'parameter_list', 'bracketed_parameter_list')
    if parameters is None:
        return ''
    types = []
    for parameter in parameters.named_children:
        if parameter.type != 'parameter':
            continue
        kind = parameter.child_by_field_name('type')
        modifiers = [node_text(data, c) for c in parameter.children if c.type in {'ref', 'out', 'in'} or c.type == 'modifier' and node_text(data, c) in {'ref', 'out', 'in'}]
        types.append(' '.join([*modifiers, node_text(data, kind) if kind is not None else '?']))
    left, right = ('[', ']') if parameters.type == 'bracketed_parameter_list' else ('(', ')')
    return left + ','.join(types) + right


def _member_name(data, node):
    if node.type == 'accessor_declaration':
        owner = node.parent.parent
        keyword = next(c.type for c in node.children if c.type in {'get', 'set', 'init', 'add', 'remove'})
        return keyword + '_' + (_name(data, owner) or 'this') + _parameters(data, owner)
    if node.type in {'property_declaration', 'indexer_declaration'}:
        return 'get_' + (_name(data, node) or 'this') + _parameters(data, node)
    name = _name(data, node)
    interface = child_of_type(node, "explicit_interface_specifier")
    if interface is not None:
        name = node_text(data, interface) + name
    if node.type == 'destructor_declaration':
        name = "~" + name
    if node.type == 'operator_declaration':
        operator = node.child_by_field_name('operator')
        name = 'operator ' + (node_text(data, operator) if operator is not None else '?')
    elif node.type == 'conversion_operator_declaration':
        kind = node.child_by_field_name('type')
        name = 'operator ' + (node_text(data, kind) if kind is not None else '?')
    parameters = child_of_type(node, 'type_parameter_list')
    if parameters is not None:
        name += node_text(data, parameters)
    return name + _parameters(data, node)


def functions_in_source(source: str, path: str, project_root: str | None = None) -> list[Function]:
    del project_root
    data, tree = parse(source, 'csharp')
    if tree.root_node.has_error:
        raise ValueError(f'C# syntax could not be parsed: {path}')
    found = []
    for node in descendants(tree.root_node):
        if node.type not in _MEMBERS | {'property_declaration', 'indexer_declaration'}:
            continue
        body = child_of_type(node, 'block', 'arrow_expression_clause')
        if body is None:
            continue
        found.append(Function(
            name=_member_name(data, node), namespace=_namespace(data, node, tree.root_node),
            complexity=complexity(body, _decision, lambda n: n.type in _TYPES),
            start_line=start_line(node), end_line=end_line(node), path=path,
            language='csharp', start_byte=node.start_byte, end_byte=node.end_byte,
        ))
    globals_ = [n for n in tree.root_node.named_children if n.type == 'global_statement']
    if globals_:
        found.append(Function(
            name='<Main>', namespace='Program',
            complexity=1 + sum(complexity(n, _decision, lambda _: False) - 1 for n in globals_),
            start_line=start_line(globals_[0]), end_line=end_line(globals_[-1]),
            path=path, language='csharp', start_byte=globals_[0].start_byte, end_byte=globals_[-1].end_byte,
        ))
    return found
