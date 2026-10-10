from django.urls import reverse


def crumbs(*items):
    trail = [{'label': 'Home', 'url': reverse('dashboard:home')}]
    trail.extend(items)
    return trail
