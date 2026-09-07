"""Channel template contracts run with stdlib only in the public checkout."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_channel_skills as skills


class ChannelSkillTests(unittest.TestCase):
    def test_coordinates_and_user_json_render_without_guessing(self):
        source = ('/{{CLI}}-review {{CLI}} --data-file {文件路径}\n'
                  '{{DATA_DIR}}/draft.json {{TOKEN_DIR}} {{MANIFEST_URL}}\n'
                  '{{INSTALL_URL}}.ps1 {{INSTALL_PS1_KEY}} {{INSTALL_SH_KEY}}\n'
                  '{{APP_NAME}}-<plat>.zip {{COPY_CONTRACT}} {"config":{"x":1}}')
        for channel, cli, data, token, app, suffix in (
            ('stable', 'redbeacon', '~/.redbeacon', '~/.bytestaff', 'RedBeacon', ''),
            ('test', 'redbeacon-test', '~/.redbeacon_test', '~/.bytestaff_test', 'RedBeacon_test', '-test'),
        ):
            with self.subTest(channel=channel):
                expected = (f'/{cli}-review {cli} --data-file {{文件路径}}\n'
                            f'{data}/draft.json {token} {skills.CENTRAL_ORIGIN}/projects/redbeacon/{channel}/latest.json\n'
                            f'https://bytestaff.jiomig.com/{cli}/install.ps1 installers/install{suffix}.ps1 installers/install{suffix}.sh\n'
                            f'{app}-<plat>.zip redbeacon_copy_v1 {{"config":{{"x":1}}}}')
                self.assertEqual(skills.render_text(source, channel), expected)

    def test_new_literals_unknown_and_incomplete_placeholders_fail(self):
        for source in ('redbeacon --version', '/redbeacon-review', '~/.redbeacon/new',
                       r'C:\Users\name\.bytestaff\token', 'installers/install.sh',
                       '{{MANFEST_URL}}', '{{CLI', '{{cli}}', 'CLI}}'):
            for channel in ('stable', 'test'):
                with self.subTest(source=source, channel=channel), self.assertRaises(ValueError):
                    skills.render_text(source, channel)

    def test_cross_channel_output_is_rejected_including_shared_product_slug(self):
        for own, other in (('stable', 'test'), ('test', 'stable')):
            variables = skills.channel_variables(other)
            for key in ('CLI', 'DATA_DIR', 'TOKEN_DIR', 'MANIFEST_URL', 'INSTALL_URL',
                        'INSTALL_SH_KEY', 'INSTALL_PS1_KEY'):
                with self.subTest(own=own, key=key), self.assertRaises(ValueError):
                    skills.validate_rendered(variables[key], own)
        with self.assertRaises(ValueError):
            skills.render_text('{{CLI}}', 'beta')

    def test_all_sources_generate_matching_commands_and_portable_bodies(self):
        with tempfile.TemporaryDirectory() as temp:
            for channel in ('stable', 'test'):
                root = Path(temp) / channel
                commands = skills.build(channel, root)
                self.assertEqual(len(commands), len(list(skills.SRC_DIR.glob('redbeacon*.md'))))
                for command in commands:
                    text = command.read_text(encoding='utf-8')
                    skills.validate_rendered(text, channel)
                    portable = root / 'agent-skills' / command.stem / 'SKILL.md'
                    self.assertEqual(portable.read_text(encoding='utf-8'), skills.portable_skill_text(command.stem, text))
                    self.assertIn(f'name: {command.stem}\n', portable.read_text(encoding='utf-8'))
            self.assertEqual(set(skills.SUPPORTED_ASSISTANTS),
                             {'claude-code', 'codex', 'openclaw', 'hermes', 'workbuddy'})

    def test_bad_source_preserves_previously_built_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            (source / 'redbeacon.md').write_text('{{UNKNOWN}}', encoding='utf-8')
            existing = root / 'output' / '.claude' / 'commands' / 'redbeacon.md'
            existing.parent.mkdir(parents=True)
            existing.write_text('previous verified output', encoding='utf-8')
            with patch.object(skills, 'SRC_DIR', source), self.assertRaises(ValueError):
                skills.build('test', root / 'output')
            self.assertEqual(existing.read_text(encoding='utf-8'), 'previous verified output')


if __name__ == '__main__':
    unittest.main()
