from django import template
from datetime import datetime
register = template.Library()


@register.filter
def index(indexable, i):
    return indexable[i]


@register.filter
def get_color(indexable, i):
    return indexable[i].backgroundColor


@register.filter
def get_group_id(obj, connections):
    try:
        pk = connections[obj.pk]
    except KeyError:
        pk = None
    return pk


@register.filter
def connection_group(obj, lst_group_conns):
    try:
        lst = lst_group_conns[obj.pk]
    except KeyError:
        lst = []
    return lst


@register.filter
def group_is_open(obj, group_open):
    try:
        res = group_open[obj.pk]
    except KeyError:
        res = False
    return res


@register.simple_tag(takes_context=True)
def progress_cell(context):
    return context['groups_progress'][context['activity'].pk][context['j']]


@register.simple_tag(takes_context=True)
def progress_cell_add(context):
    return context['groups_progress_add']


@register.simple_tag(takes_context=True)
def get_symbols(context):
    if context['activity'].cellsComments:
        cells_comments = [act.split('*') for act in context['activity'].cellsComments.split('|')]
        return cells_comments[context['j']][0]
    return ''


@register.simple_tag(takes_context=True)
def get_comments(context):
    if context['activity'].cellsComments:
        cells_comments = [act.split('*') for act in context['activity'].cellsComments.split('|')]
        return cells_comments[context['j']][1]
    return ''


@register.filter
def get_days(obj):
    return obj.onOffCells.split()


@register.filter
def get_one_day(obj, day):
    return True if obj.onOffCells.split()[day] == 'True' else False


@register.simple_tag(takes_context=True)
def get_class_on(context):
    return str(context['forloop']['parentloop']['counter0']) + '-' + str(context['j']) in context['cellsToClick']


@register.simple_tag(takes_context=False)
def get_date_y_m():
    return datetime.today().strftime('%Y-%m')
