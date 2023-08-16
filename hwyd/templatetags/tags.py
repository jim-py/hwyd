from django import template
from ..models import ActivitiesConnection
register = template.Library()


@register.filter
def index(indexable, i):
    return indexable[i]


@register.filter
def get_color(indexable, i):
    return indexable[i].backgroundColor


@register.filter
def connection(obj):
    try:
        pk = ActivitiesConnection.objects.get(activity=obj).group.pk
    except ActivitiesConnection.DoesNotExist:
        pk = None
    return pk
    # return 24


@register.filter
def connection_group(obj):
    lst = []
    for elem in ActivitiesConnection.objects.filter(group=obj):
        lst.append(elem.activity.pk)
    return lst
    # return ['50']


@register.filter
def group_is_open(obj):
    try:
        res = ActivitiesConnection.objects.get(activity=obj).group.isOpen
    except ActivitiesConnection.DoesNotExist:
        res = False
    return res
    # return True


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
