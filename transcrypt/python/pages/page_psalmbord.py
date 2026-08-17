__pragma__('alias', 'S', '$')  # to use jQuery library with 'S' instead of '$'
import utils
from elements import Element, element, ElementWrapper, get_Element, get_elements, get_element
from layout import home, main, set_title
from dialogs import dialog_confirm
E = Element


# copied from fonts.py
fonts = ["Arial", "Cambria", "Courier New", "Courier Prime", "Georgia", "Gill Sans", "Verdana", "Samsung"]
fontsizes = list(range(5, 16))
fontweights = list(range(300, 900, 100))

# copied from settings.py
default_screens = ['Ps 45:1\n10 GEB:9\nRomeinen 3:1-10\nPs 89:4\nPs 103:7\nPs 116:1 2 3 4\nHC Zondag 23','']
default_fontsize = 8
refreshrates = [1,2,3,4,5,10,15,30,60]


class Select(ElementWrapper):
    def __init__(self, name: str, values: dict):
        super().__init__(element('select'))
        self.attr('name', name)
        for v in values:
            self.append(E('option').attr('value', v).inner_html(v))


class Page(ElementWrapper):
    def __init__(self):
        super().__init__(element('div'))
        self.psalmbord: dict = None

        width_1 = 'col-sm-1'
        width_2 = 'col-sm-2'
        width_3 = 'col-sm-3'

        def set_inputs():
            select_fontfamily.element.value = self.psalmbord['fontfamily']
            select_fontweight.element.value = self.psalmbord['fontweight']
            select_refreshrate.element.value = self.psalmbord['refreshrate']

            i = 0
            for t in self.psalmbord['screens']:
                ## idealiter zou ik de screen_index list opruimen, 
                ## maar hoe check ik anders of het item uit self.psalmbord['screens'] al op de pagina toegevoegd is?
                if i not in screen_index and t:
                    add_screen('', i, t['text'], t['size'], self.psalmbord['active'])
                elif i == self.psalmbord['active']:
                    # set active screen checked
                    screens = screen_div.element.querySelectorAll(".screen")
                    screens[i].querySelector("input").checked = True

                    # if the saved font size differs from this active screen, it must be updated
                    # the difference can be caused by removing an active screen
                    # screen 1 'met regels' then becomes active automatically
                    fontsize = screens[i].querySelector("select").value
                    if self.psalmbord['fontsize'] != fontsize:
                        self.psalmbord['fontsize'] = fontsize
                        save_changes()
                i = i + 1

        async def save_changes():
            self.psalmbord = await utils.post(utils.get_url('general/setPsalmbord'), self.psalmbord)
            set_inputs()

        # add screen
        def add_screen(evt, i = None, text = '', fontsize = default_fontsize, active = None):
            if i is None:
                i = screen_div.element.querySelectorAll(".screen").length
            screen_index.append( i )

            select_fontsize = Select(f"fontsize{i}",fontsizes)
            select_fontsize.element.value = fontsize
            select_fontsize.element.onchange = onchange

            id = f'screen{i}'
            div = E('div').attr('class','{} screen'.format(width_2)).attr('data-id',i)
            
            s = E("input").attr("class", "form-control").attr('id',id).attr("type", "radio").attr('name','active')
            if i == active:
                s.element.checked = True
            s.element.onchange = onchange
            
            f = E('div').attr('style','clear:both').append(
                    E('label').attr('style', 'width:60%').inner_html("Aantal regels"),
                    E('div').attr('style', 'display:inline-block;width:39%').append(select_fontsize)
                )
            
            d = E('button').attr('class','btn btn-danger btn-sm').attr('style','float:right; margin: 5px 0;').append( E('i').attr("class", 'fas fa-trash-alt') )
            d.element.onclick = delete_screen

            t = E('textarea').attr('name',id)
            t.element.value = text
            t.element.onchange = onchange

            div.append(s,d,f,t)
            screen_div.append( div )
            
            self.psalmbord['screens'][i] = {'index':id,'text':text,'size':fontsize}

        def delete_screen(evt):
            evt.target.closest(".screen").remove()
            onchange()

        # show output frame
        screen_div = E('div').attr('class','row')
        screen_div.append(
            E('div').attr('style', 'float: left; width: 270px;').append(
                E('iframe').attr('src', '/psalmbord').attr('style', 'width: 270px; height: 480px; border: none;')
            )
        )

        select_fontfamily = Select("fontfamily", fonts)
        select_fontweight = Select("fontweight", fontweights)
        select_refreshrate = Select("refreshrate", refreshrates)
        screen_index = [] # nog nodig?

        button_add_screen = E('button').attr('class', 'btn btn-primary btn-sm').inner_html("Scherm toevoegen")
        button_add_screen.element.onclick = add_screen

        self.append(screen_div)
        self.append(button_add_screen)

        # spacer
        self.append( E('p').attr('class','psalmbord_heading').inner_html('Instellingen') )

        # config settings
        self.append(
            E('div').attr('class', 'form-group row').append(
                E('label').attr('class', '{} col-form-label'.format(width_2)).inner_html("Lettertype"),
                E('div').attr('class', '{}'.format(width_3)).append(select_fontfamily)
            ),
            E('div').attr('class', 'form-group row').append(
                E('label').attr('class', '{} col-form-label'.format(width_2)).inner_html("Letterdikte"),
                E('div').attr('class', '{}'.format(width_3)).append(select_fontweight)
            ),
            E('div').attr('class', 'form-group row').append(
                E('label').attr('class', '{} col-form-label'.format(width_2)).inner_html("Verversen per ... seconden"),
                E('div').attr('class', '{}'.format(width_3)).append(select_refreshrate)
            ),
        )

        # help
        self.append( E('p').attr('class','psalmbord_heading').inner_html('Uitleg') )
        self.append( 
            E('ul').append(
                E('li').inner_html("Begin een regel met _ om te centreren"),
                E('li').inner_html("Gebruik een : om automatisch uit te lijnen"),
                E('li').inner_html("Gebruik een ; om niet automatisch uit te lijnen, de ; wordt als : getoond"),
                E('li').inner_html("Voeg een leeg scherm toe om psalmbord eenvoudig 'op zwart' te zetten"),
            )
        )

        async def initialize():
            self.psalmbord = await utils.post(utils.get_url('general/getPsalmbord'), {})
            set_inputs()

        self.refresh = initialize

        async def onchange(evt):
            self.psalmbord['fontfamily'] = select_fontfamily.element.value
            self.psalmbord['fontsize'] = default_fontsize # default value, will be updated
            self.psalmbord['fontweight'] = select_fontweight.element.value
            self.psalmbord['active'] = 1 # default value, will be updated
            self.psalmbord['refreshrate'] = select_refreshrate.element.value
            self.psalmbord['screens'] = []

            i = 0
            for s in screen_div.element.querySelectorAll(".screen"):
                select_fontsize = s.querySelector("select")
                text = s.querySelector("textarea")
                
                if s.querySelector("input").checked:
                    self.psalmbord['active'] = i
                    self.psalmbord['fontsize'] = select_fontsize.value if select_fontsize else default_fontsize

                t = text.value if text else default_screens[i]
                f = select_fontsize.value if select_fontsize else default_fontsize

                self.psalmbord['screens'].append({'index':f"screen{i}",'text':t,'size':f})
                i = i + 1
            save_changes()

        select_fontfamily.element.onchange = onchange
        select_fontweight.element.onchange = onchange
        select_refreshrate.element.onchange = onchange

    def show(self):
        main.remove_childs()
        main.append(self)
        self.refresh()
