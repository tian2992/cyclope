from django.shortcuts import render, redirect
from django import forms
from cyclope.apps.medialibrary.models import Picture, BaseMedia, SoundTrack
from cyclope.apps.medialibrary.forms import InlinedPictureForm
from django.views.decorators.http import require_POST
from django.core.urlresolvers import reverse
from forms import MediaWidgetForm, MediaEmbedForm
from filebrowser.functions import handle_file_upload, convert_filename
from django.conf import settings
import os
from filebrowser.settings import ADMIN_THUMBNAIL
from cyclope.utils import generate_fb_version
from django.contrib import messages
from django.http import HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from cyclope.apps.articles.models import Article
from cyclope.models import RelatedContent
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from models import MediaWidget
from django.utils.translation import ugettext_lazy as _
from filebrowser.base import FileObject
from datetime import datetime
# an other good reason to merge media apps:
from cyclope.apps.related_admin.views import staff_required


###########################
##Article's pictures widget

# for new Article
# GET /pictures/new
@staff_required
def pictures_new(request):
    #Model
    article = Article()
    #Forms
    form = MediaWidgetForm()
    #TODO(NumericA) picture_select&delete forms

    # defaults for new articles, after it's javascript's
    pictures = Picture.objects.all().order_by('-creation_date')
    article_pictures = []

    # pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(pictures, nRows)
    select_page = paginator.page(n)

    # parent admin pictures widget refresh
    refresh_widget = request.session.pop('refresh_widget', False)

    # for new articles
    new_picture = request.session.pop('new_picture', None)
    remove_picture = request.session.pop('remove_picture', None)
   
    return render(request, 'media_widget/pictures_widget.html', {
        'form': form, 
        'refresh_widget': refresh_widget,
        'select_page': select_page,
        'delete_page': article_pictures,
        'n': n,
        'nRows': nRows,
        'new_picture': new_picture,
        'remove_picture': remove_picture
    })

# for existing Article
# GET /pictures/new/article_id
@staff_required
def pictures_upload(request, article_id):
    """ Returns widget's inner HTML to be viewed through an iframe.
        This ensures bootstrap styles isolation."""
    #Model
    article = Article.objects.get(pk=article_id)
    #Forms
    form = MediaWidgetForm()
    #TODO(NumericA) picture_select
    #TODO(NumericA) picture_delete

    #picture selection
    all_pictures = Picture.objects.all().order_by('-creation_date')
    article_pictures = article.pictures.all()
    pictures = [picture for picture in all_pictures if not picture in article_pictures]
    
    # pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(pictures, nRows)
    select_page = paginator.page(n)
    #TODO(NumericA) delete_page pagination
        
    # parent admin pictures widget refresh
    refresh_widget = request.session.pop('refresh_widget', False)

    return render(request, 'media_widget/pictures_widget.html', {
        'form': form, 
        'article_id': article_id,
        'refresh_widget': refresh_widget,
        'select_page': select_page,
        'delete_page': article_pictures ,
        'n': n,
        'nRows': nRows,
        'param': article_id,
    })


# POST /pictures/create/article_id
@require_POST
@staff_required
def pictures_create(request, article_id):
    form = MediaWidgetForm(request.POST, request.FILES)
    if article_id:
        article = Article.objects.get(pk=article_id)
    if form.is_valid():
        image = form.cleaned_data['image']
        # handle file upload
        objeto = handle_file_save("pictures", image)
        # database save
        picture = Picture(
            name = form.cleaned_data['name'] if form.cleaned_data['name']!='' else image.name,
            description = form.cleaned_data['description'],
            image = objeto
        )
        if article_id:
            picture.user = article.user
            picture.author = article.author
            picture.source = article.source
        picture.save()

        messages.success(request, _('Loaded image : %s' % image.name))
        request.session['refresh_widget'] = True

        if article_id:
            _associate_picture_to_article(article, picture)
            return redirect('pictures-upload', article_id)
        else:
            request.session['new_picture'] = str(picture.id)
            return redirect('pictures-new')
    else:
        # picture selection
        pictures_list = Picture.objects.all().order_by('-creation_date')
        # pagination
        n, nRows = _paginator_query_string(request)
        paginator = Paginator(pictures_list, nRows)
        select_page = paginator.page(n)
        if article_id:
            article_pictures = article.pictures.all()
        else:
            article_pictures = []
        #
        return render(request, 'media_widget/pictures_widget.html', {
            'form': form, 
            'article_id': article_id,
            'select_page': select_page,
            'delete_page': article_pictures ,
            'n': n,
            'nRows': nRows,
            'param': article_id,
            'refresh_widget': True
        })
        
#POST /pictures/update/article_id
# TODO(NumericA) update multiple pictures
@require_POST
@staff_required
def pictures_update(request, article_id):
    picture_id = int(request.POST.get('picture_id'))
    picture = Picture.objects.get(pk=picture_id)
    
    messages.success(request, _('Selected image : %s' % picture.name))
    request.session['refresh_widget'] = True
    
    if article_id:
        article = Article.objects.get(pk=article_id)    
        _associate_picture_to_article(article, picture)
        return redirect('pictures-upload', article_id)
    else:
        request.session['new_picture'] = str(picture.id)
        return redirect('pictures-new')

#POST /pictures/delete/article_id
@staff_required
def pictures_delete(request, article_id):
    picture_id = request.POST['picture_id']
    picture = Picture.objects.get(pk=picture_id)

    messages.warning(request, _('Deleted image: %s' % picture.name))
    request.session['refresh_widget'] = True
    
    if article_id:
        article = Article.objects.get(pk=article_id)    
        article.pictures.remove(picture_id)
        return redirect('pictures-upload', article_id)
    else:
        request.session['remove_picture'] = str(picture.id)
        return redirect('pictures-new')

#GET /pictures/widget/article_id
@staff_required
def pictures_widget(request, article_id):
    """
    Ajax call to this method refreshes Article Admin's pictures widget thumbnails.
    """
    article = Article.objects.get(pk=article_id)
    pictures_list = [picture.id for picture in article.pictures.all()]
    html = MediaWidget().render("pictures", pictures_list)
    return HttpResponse(html)        

#GET /pictures/widget/1,11,2, (comma separated pictures ids)
@staff_required
def pictures_widget_new(request, pictures_ids):
    """
    Same as above but receives comma separated pictures ids to let them as inputs for save.
    """
    pictures_list = [int(x) for x in pictures_ids.split(',') if x]
    html = MediaWidget().render("pictures", pictures_list)
    return HttpResponse(html)

# GET /pictures/widget/3,2, (comma separated pictures ids)
@staff_required
def pictures_widget_select(request, pictures_ids):
    """
    Opposite as above: returns all Pictures except those in the picture ids list.
    """
    def no_nulo(x): return x!='' and x is not None
    pictures_ids = filter(no_nulo, pictures_ids.split(','))
    pictures = Picture.objects.exclude(pk__in=pictures_ids).order_by('-creation_date')
    
    # pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(pictures, nRows)
    select_page = paginator.page(n)
    
    return render(request, 'media_widget/picture_select.html', {
        'select_page': select_page,
        'n': n,
        'nRows': nRows,
    })

# GET pictures/delete_list/7,5,3,1
@staff_required
def delete_pictures_list(request, pictures_ids):
    """
    For new articles:
    Render a delete form with specified picture ids
    """
    #TODO(NumericA) delete_form
    pictures_list = [int(x) for x in pictures_ids.split(',') if x]
    pictures = [Picture.objects.get(pk=x) for x in pictures_list]
    #TODO(NumericA) pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(pictures, nRows)
    delete_page = paginator.page(n)
    return render(request, 'media_widget/picture_delete.html', {
        'delete_page': delete_page,
        'n': n,
        'nRows': nRows,
    })


####################
##Embed Media Widget

#GET /embed/new/picture
@staff_required
def embed_new(request, media_type):
    # file upload form
    form = MediaEmbedForm()
    # media selection list
    media_list = _fetch_selection_from_library(media_type)
    # pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(media_list, nRows)
    pagina = paginator.page(n)
    # render
    return render(request, 'media_widget/media_widget.html', {
        'form': form,
        'pagina': pagina,
        'n': n,
        'nRows': nRows,
        'media_type': media_type,
        'param': media_type
    })

#POST /embed/create
@require_POST
@staff_required
def embed_create(request):
    form = MediaEmbedForm(request.POST, request.FILES)
    if form.is_valid():
        multimedia = form.cleaned_data['multimedia']
        media_type = form.cleaned_data['media_type']
        if _validate_file_type(media_type, multimedia):
            klass = ContentType.objects.get(model=media_type).model_class()
            instance = klass() # generic instance of media model
            #filesystem save 
            objeto = handle_file_save(instance.directory, multimedia)
            # database save
            instance.name = form.cleaned_data['name'] if form.cleaned_data['name']!='' else multimedia.name
            instance.description = form.cleaned_data['description']
            instance.user = request.user
            setattr(instance, klass.media_file_field, objeto)
            instance.save()
            #response
            return render(request, 'media_widget/media_widget.html', {
                'form': form,
                'current_object': instance,
                'file_url': instance.media_file,
                'media_type': media_type,
            })
        else:
            msg = _validation_error_message(multimedia, media_type)
            messages.error(request, msg)
            return render(request, 'media_widget/media_widget.html', {
                'form': form,
            })
    else:
        return render(request, 'media_widget/media_widget.html', {
            'form': form, 
        })

# GET /library/media_type?n=1&nRows=5
@staff_required
def library_fetch(request, media_type):
    """
    Query Media objects list according to selected media content type.
    Return them as the HTML to render to refresh the area.
    This method could also search?
    """
    # media selection list
    media_list = _fetch_selection_from_library(media_type)
    # pagination
    n, nRows = _paginator_query_string(request)
    paginator = Paginator(media_list, nRows)
    pagina = paginator.page(n)
    # response
    return render(request, 'media_widget/media_select.html', {
        'pagina': pagina,
        'n': n,
        'nRows': nRows,
        'param': media_type,
        'media_type': media_type,
    })

########
#HELPERS

def _associate_picture_to_article(article, picture):
    """Helper method to DRY picture create and update"""
    #add picture to current Article's
    article.pictures.add(picture)
    #article as Picture's related content
    related = RelatedContent(
        self_object = picture,
        other_object = article
    )
    related.save()
    
# what about validating file extensions in javascript?
def _validate_file_type(media_type, multimedia):
    """
    Validate uploaded file MIME type matches intended Content Type.
    Allowed MIME types are different than FileBrowser's because they're the ones allowed by HTML5.
    """
    if media_type == 'picture':
        top_level_mime, mime_type = tuple(multimedia.content_type.split('/'))
        return top_level_mime == 'image' # allow all image types FIXME?
    else:
        if media_type == 'soundtrack': #TODO(NumericA) relax checks
            allowed_mime_types = ['audio/mpeg', 'audio/ogg', 'audio/wav']
        elif media_type == 'movieclip':
            allowed_mime_types = ['video/mp4', 'video/webm', 'video/ogg']
        elif media_type == 'document':
            allowed_mime_types = ['application/pdf']
        elif media_type == 'flashmovie':
            allowed_mime_types = ['x-shockwave-flash', 'x-flv']
        else:
            return False
        return multimedia.content_type in allowed_mime_types

def _validation_error_message(multimedia, media_type):
    """
    Error message string for MIME type server-side validation
    """
    type_name = {
        'picture': 'Image',
        'soundtrack': 'Audio',
        'movieclip': 'Video',
        'document': 'PDF',
        'flashmovie': 'Flash'
    }
    msg = _("%(real_type)s is not a valid %(desired_type)s type!") % {'real_type': multimedia.content_type, 'desired_type': type_name[media_type]}
    return msg
    
# this function can also be used for search
def _fetch_selection_from_library(media_type):
    """
    Returns media lists filtered by content type
    For selection in Embed Widget search tab.
    Shared by embed_new & select_type actions.
    """
    media_list = ContentType.objects.get(model=media_type).get_all_objects_for_this_type().order_by('-creation_date')
    return media_list
    
def _paginator_query_string(request):
    """
    Interpret ?n=1&nRows=5 query string
    """
    if request.GET.has_key(u'n'):
            n = request.GET[u'n']  #url query string
    else:
        n = 1 #defaults to first
    if request.GET.has_key(u'nRows'):
        nRows = request.GET[u'nRows']  #url query string
    else:
        nRows = 5
    return (n, nRows)
    
def _get_todays_folder(path):
    """
    generate path/year/month directory structure
    ex. /media/pictures/2016/8
    """
    return path+"/{:%Y/%m}".format(datetime.now())

def handle_file_save(directory, multimedia):
    """ DRY file upload for pictures_create and embed_create """
    # normalize file name
    multimedia.name = convert_filename(multimedia.name)
    multimedia_folder = _get_todays_folder(directory)
    abs_path = os.path.join(settings.MEDIA_ROOT, multimedia_folder)
    uploaded_path = handle_file_upload(abs_path, multimedia)
    # uploaded path can be different from name ex. if path already exists
    uploaded_path_name = uploaded_path.split(multimedia_folder)[1]
    url = "%s/%s" % (multimedia_folder, uploaded_path_name)
    url = url.replace('//','/')
    objeto = FileObject(url)
    return objeto
