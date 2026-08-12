"""
Чтение файлов Microsoft Project (.mpp) через MPXJ + JPype.
Адаптировано из проекта Проверка.
"""

import sys
import io
import os
import glob
import shutil
import tempfile
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def setup_jvm():
    import jpype
    import jpype.imports

    if jpype.isJVMStarted():
        return

    mpxj_lib = os.path.join(os.path.dirname(__import__('mpxj').__file__), 'lib')
    for jar in glob.glob(os.path.join(mpxj_lib, '*.jar')):
        jpype.addClassPath(jar)

    jdk_home = os.environ.get('JAVA_HOME', '')
    if not jdk_home:
        import jdk
        jdk_home = jdk.install('17')

    jvm_dll = os.path.join(jdk_home, 'bin', 'server', 'jvm.dll')
    if not os.path.exists(jvm_dll):
        import jdk
        jdk_home = jdk.install('17')
        jvm_dll = os.path.join(jdk_home, 'bin', 'server', 'jvm.dll')

    jpype.startJVM(jvm_dll, '-Dfile.encoding=UTF-8')


def read_mpp(file_path):
    import jpype

    setup_jvm()

    Reader = jpype.JClass('org.mpxj.reader.UniversalProjectReader')
    File = jpype.JClass('java.io.File')
    TaskField = jpype.JClass('org.mpxj.TaskField')
    UserDefinedField = jpype.JClass('org.mpxj.UserDefinedField')

    tmp_path = os.path.join(tempfile.gettempdir(), 'mpxj_temp_project.mpp')
    shutil.copy2(file_path, tmp_path)

    project = Reader().read(File(tmp_path))

    props = project.getProjectProperties()
    project_properties = {
        'title': _js(props.getProjectTitle()),
        'start_date': _js(props.getStartDate()),
        'finish_date': _js(props.getFinishDate()),
        'status_date': _js(props.getStatusDate()),
        'author': _js(props.getAuthor()),
        'manager': _js(props.getManager()),
        'company': _js(props.getCompany()),
    }

    task_custom_fields = []
    custom_field_map = {}
    try:
        custom_fields = project.getCustomFields()
        for cf in custom_fields:
            alias = _js(cf.getAlias())
            field_type = cf.getFieldType()
            if alias and field_type:
                ft_str = str(field_type)
                custom_field_map[ft_str] = alias
                if isinstance(field_type, TaskField):
                    task_custom_fields.append((field_type, alias))
                elif isinstance(field_type, UserDefinedField):
                    try:
                        ftc = str(field_type.getFieldTypeClass())
                        if ftc == 'TASK':
                            task_custom_fields.append((field_type, alias))
                    except Exception:
                        pass
    except Exception:
        pass

    java_tasks = project.getTasks()
    tasks = {}
    for i in range(java_tasks.size()):
        t = java_tasks.get(i)
        if not t:
            continue
        tid = int(str(t.getID())) if t.getID() is not None else i

        parent_task = t.getParentTask()
        parent_id = int(str(parent_task.getID())) if parent_task and parent_task.getID() is not None else None

        resource_names = []
        try:
            assignments = t.getResourceAssignments()
            if assignments:
                for a_idx in range(assignments.size()):
                    a = assignments.get(a_idx)
                    r = a.getResource()
                    if r and r.getName():
                        resource_names.append(str(r.getName()))
        except Exception:
            pass

        custom = {}
        for ft, alias in task_custom_fields:
            val = _js(t.get(ft))
            if val:
                custom[alias] = val

        tasks[tid] = {
            'id': tid,
            'unique_id': int(str(t.getUniqueID())) if t.getUniqueID() else None,
            'name': _js(t.getName()),
            'outline_level': int(str(t.getOutlineLevel())) if t.getOutlineLevel() is not None else 0,
            'parent_id': parent_id,
            'duration': _js(t.getDuration()),
            'start': _js(t.getStart()),
            'finish': _js(t.getFinish()),
            'milestone': bool(t.getMilestone()) if t.getMilestone() is not None else False,
            'critical': bool(t.getCritical()) if t.getCritical() is not None else False,
            'summary': bool(t.getSummary()) if t.getSummary() is not None else False,
            'constraint_type': _js(t.getConstraintType()),
            'deadline': _js(t.getDeadline()),
            'baseline_start': _js(t.getBaselineStart()),
            'baseline_finish': _js(t.getBaselineFinish()),
            'actual_start': _js(t.getActualStart()),
            'actual_finish': _js(t.getActualFinish()),
            'percent_complete': _num(t.getPercentageComplete()),
            'start_variance': _dur_days(t.getStartVariance()),
            'finish_variance': _dur_days(t.getFinishVariance()),
            'total_slack': _js(t.getTotalSlack()),
            'total_slack_days': _dur_days(t.getTotalSlack()),
            'free_slack': _js(t.getFreeSlack()),
            'free_slack_days': _dur_days(t.getFreeSlack()),
            'resource_names': '; '.join(resource_names) if resource_names else None,
            'custom_fields': custom if custom else None,
        }

    relations = []
    for i in range(java_tasks.size()):
        t = java_tasks.get(i)
        if not t:
            continue
        preds = t.getPredecessors()
        if not preds:
            continue
        for j in range(preds.size()):
            rel = preds.get(j)
            pred_task = rel.getPredecessorTask()
            succ_task = rel.getSuccessorTask()
            relations.append({
                'from': int(str(pred_task.getID())) if pred_task else None,
                'to': int(str(succ_task.getID())) if succ_task else None,
                'type': _js(rel.getType()),
                'lag': _js(rel.getLag()),
            })

    os.remove(tmp_path)

    return {
        'project_properties': project_properties,
        'tasks': tasks,
        'relations': relations,
        'custom_field_aliases': custom_field_map,
        'stats': {
            'total_tasks': len(tasks),
            'total_relations': len(relations),
            'critical_tasks': sum(1 for t in tasks.values() if t.get('critical')),
            'milestones': sum(1 for t in tasks.values() if t.get('milestone')),
            'summary_tasks': sum(1 for t in tasks.values() if t.get('summary')),
        }
    }


def _js(java_obj):
    if java_obj is None:
        return None
    return str(java_obj)


def _num(java_obj):
    if java_obj is None:
        return None
    try:
        return float(str(java_obj))
    except (ValueError, TypeError):
        return None


def _dur_days(java_dur):
    if java_dur is None:
        return None
    try:
        val = float(str(java_dur.getDuration()))
        units = str(java_dur.getUnits()).upper()
        if 'HOUR' in units:
            return round(val / 8.0, 1)
        elif 'WEEK' in units:
            return round(val * 5.0, 1)
        elif 'MONTH' in units:
            return round(val * 20.0, 1)
        elif 'MINUTE' in units:
            return round(val / 480.0, 1)
        else:
            return round(val, 1)
    except Exception:
        return None


def shutdown():
    import jpype
    if jpype.isJVMStarted():
        jpype.shutdownJVM()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python read_mpp.py <path_to.mpp> [output.json]")
        sys.exit(1)

    data = read_mpp(sys.argv[1])

    print(f"Project: {data['project_properties']['title']}")
    print(f"Tasks: {data['stats']['total_tasks']} (critical: {data['stats']['critical_tasks']})")
    print(f"Custom fields: {list(data.get('custom_field_aliases', {}).values())}")

    if len(sys.argv) > 2:
        with open(sys.argv[2], 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved to: {sys.argv[2]}")

    shutdown()
