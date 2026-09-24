"""Fixed primary runtime reassessment, existing workloads, no tuning."""
SCENES = ('corridor_neon', 'forest_outpost', 'barrier_yard', 'reflective_plaza', 'hud_particles')
CONTROLS = ('bicubic', 'always', 'fixed2', 'scheduler')


def schedule(repetitions=2):
    assert repetitions in (1, 2)
    first = []
    for scene_index, scene in enumerate(SCENES):
        for mode_index, width in enumerate((160,)):
            offset = scene_index % 4
            controls = CONTROLS[offset:] + CONTROLS[:offset]
            first.extend(dict(scene=scene, width=width, control=control, mode='prompt') for control in controls)
    return [dict(row, repetition=rep + 1) for rep in range(repetitions)
            for row in (first if rep == 0 else first[::-1])]


def cell_name(index, row):
    return f'{index:02d}_r{row["repetition"]}_{row["scene"]}_{row["width"]}_{row["control"]}'


def replace_option(command, option, value):
    matches = [i for i, arg in enumerate(command) if arg.startswith(option + '=')]
    assert len(matches) == 1, (option, matches)
    command[matches[0]] = option + '=' + str(value)


def adapt_command(command, row, project):
    command = list(command)
    command[command.index('--path') + 1] = str(project)
    replace_option(command, '--scene-variant', row['scene'])
    replace_option(command, '--neural-refresh-period-frames', 2 if row['control'] == 'fixed2' else 1)
    assert '--selection-mode=prompt' in command
    replace_option(command, '--mode', 'mode_90p_to_180p')
    replace_option(command, '--native-bridge-model', project.parent / 'model.rknn')
    if row['control'] == 'scheduler':
        replace_option(command, '--neural-refresh-policy', project.parent / 'policy.json')
    return command
