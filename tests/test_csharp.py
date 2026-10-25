from pathlib import Path

import pytest

from crapper.coverage import load_bundle
from crapper.discover import iter_source_files, language_of
from crapper.languages import functions_in_file


def functions(source):
    return functions_in_file('csharp', source, 'src/Box.cs', '/project')


def test_members_namespace_overloads_and_byte_spans():
    source = '''namespace Demo.Core;
public record Box<T>(T Value) {
 public Box() { if (true) {} }
 public int Pick(int x) => x > 0 ? x : 0;
 public int Pick(string x) { int Local() => 1; return x?.Length ?? 0; }
 public int Value2 { get => 1; set { if(value > 0) {} } }
 public int Plain { get; set; }
 public int Result => 1;
 public int this[int i] => i;
 public class Inner { public void Work() {} }
}
'''
    found = functions(source)
    assert {f.name for f in found} == {'Box()', 'Pick(int)', 'Pick(string)', 'get_Value2', 'set_Value2', 'get_Result', 'get_this[int]', 'Work()'}
    assert {f.namespace for f in found} == {'Demo.Core.Box<T>', 'Demo.Core.Box<T>.Inner'}
    assert {f.name: f.complexity for f in found}['Pick(string)'] == 3
    for fn in found:
        assert fn.start_byte >= 0 and fn.end_byte > fn.start_byte
        assert source.encode()[fn.start_byte:fn.end_byte]


def test_nested_namespace_and_expression_switch():
    found = functions('namespace A { namespace B { class C { int F(int x) => x switch { 1 or 2 => 3, _ => 0 }; } } }')
    assert found[0].namespace == 'A.B.C'
    assert found[0].complexity == 4  # two arms and the or-pattern, plus the entry


def test_skip_generated_build_output_and_test_projects(tmp_path):
    for name in ('src/Code.cs', 'src/obj/Generated.cs', 'src/bin/Copy.cs', 'src/Code.g.cs', 'Foo.Tests/UnitTest.cs'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('class C { void F() {} }')
    assert language_of('src/Code.cs') == 'csharp'
    assert [p.name for p in iter_source_files([tmp_path])] == ['Code.cs']


def test_cobertura_async_lines_branches_and_multiple_reports(tmp_path):
    path = tmp_path / 'coverage/one/coverage.cobertura.xml'
    path.parent.mkdir(parents=True)
    path.write_text('''<coverage><packages><package><classes>
    <class name="Demo.C" filename="src/Box.cs"><lines>
    <line number="3" hits="0" branch="true" condition-coverage="50% (1/2)"/>
    <line number="4" hits="1"/>
    </lines></class>
    <class name="Demo.C/&lt;F&gt;d__0" filename="src/Box.cs"><lines><line number="3" hits="1"/></lines></class>
    </classes></package></packages></coverage>''')
    source = 'namespace Demo;\nclass C {\n int F(int x) { if(x > 0) return x;\n return 0; }\n}'
    fn = functions(source)[0]
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(fn) == 50.0
    assert bundle.lcov['src/Box.cs'][3] == (1, 1)


def test_invalid_csharp_is_reported():
    with pytest.raises(ValueError, match='C# syntax'):
        functions('class C { void F( { }')


def test_failed_csharp_coverage_cannot_write_green_metrics(tmp_path, monkeypatch):
    from crapper.cli import run
    (tmp_path / 'C.cs').write_text('class C { int F() => 1; }')
    monkeypatch.setattr('crapper.cli.run_coverage', lambda *_a: 1)
    assert run(['--root', str(tmp_path), 'C.cs']) == 1
    assert not (tmp_path / '.metrics/crap.edn').exists()


def test_explicit_interface_and_destructor_do_not_collide():
    found = functions('class C : I { public C() {} ~C() {} void I.M() {} }')
    assert {fn.name for fn in found} == {'C()', '~C()', 'I.M()'}
