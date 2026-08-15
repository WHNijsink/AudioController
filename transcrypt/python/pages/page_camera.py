import utils
from elements import Element, element, ElementWrapper, get_Element, get_elements, get_element
from layout import home, main, set_title
E = Element

class Page(ElementWrapper):

    def __init__(self):
        super().__init__(element('div'))
        self.cameras: dict = None
        self.camid = 0

        # load wfs.js
        script = document.createElement("script")
        script.src = "/static/js/wfs.js"
        document.head.appendChild(script)

        # create html elements
        div_cams = E('div').attr('id','cams')
        
        div_live_video = E('div').attr('class','video')
        div_live_err = E('div').attr('class','errors')
        div_live_hor = E('div').attr('class','raster hor')
        div_live_ver = E('div').attr('class','raster ver')
        div_live = E('div').attr('id','live').append(div_live_err,div_live_video,div_live_hor,div_live_ver)

        div_presets = E('div').attr('id','presets')

        div_move = E('div').attr('id','move').attr('class','hidden').append(
            E('div').append(
                E('button').attr('id','leftup').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-left').attr('style','rotate: 45deg')
                ),
                E('button').attr('id','up').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-up')
                ),
                E('button').attr('id','rightup').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-right').attr('style','rotate: -45deg')
                )
            ),
            E('div').append(
                E('button').attr('id','left').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-left')
                ),
                E('button').attr('id','stop').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-stop')
                ),
                E('button').attr('id','right').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-right')
                )
            ),
            E('div').append(
                E('button').attr('id','leftdown').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-left').attr('style','rotate: -45deg')
                ),
                E('button').attr('id','down').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-down')
                ),
                E('button').attr('id','rightdown').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-arrow-right').attr('style','rotate: 45deg')
                )
            ),
            E('div').append(
                E('button').attr('id','zoomdec').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-search-minus')
                ),
                E('div').attr('class','ptzmove'),
                E('button').attr('id','zoomadd').attr('class','ptzmove btn btn-primary').append(
                    E('span').attr('class','fas fa-search-plus')
                ),
            ),
        )

        div_footer = E('div').attr('id','footer').attr('class','hidden')

        self.append(
            div_cams,
            div_live,
            div_presets,
            div_move,
            div_footer
        )

        # functies
        def btn_cameras():
            div_cams.remove_childs()
            div_presets.remove_childs()

            ul = E('ul')
            for index, cam in enumerate(self.cameras):
                btn = E('button').inner_html(cam['name']).attr('value',index).attr('class','btn btn-primary')
                btn.element.onclick = btn_presets

                ul.append(
                    E('li').append( btn )
                )
            div_cams.append( ul )

        async def btn_presets(evt):
            # initialize dom
            div_live_err.remove_childs()
            div_live_video.remove_childs()
            div_presets.remove_childs()
            div_footer.remove_childs()
            div_move.attr('class','hidden')
            div_footer.attr('class','hidden')

            # set cams.active button
            for btn in div_cams.element.querySelectorAll("button"):
                btn.classList.add("btn-primary")
                btn.classList.remove("btn-success")

            if evt:
                self.camid = int(evt.currentTarget.value)
                evt.currentTarget.classList.remove("btn-primary")
                evt.currentTarget.classList.add("btn-success")
            else:
                btn = div_cams.element.querySelector("button")
                btn.classList.remove("btn-primary")
                btn.classList.add("btn-success")
            
            # attach move events
            for btn in div_move.element.querySelectorAll("button"):
                # Stop-knop
                if btn.id == "stop":
                    btn.onclick = moveStop
                    btn.onpointerdown = moveStop
                else:
                    btn.onpointerdown = moveStart
                    btn.onpointerup = moveStop
                    btn.onpointerleave = moveStop
                    btn.onpointercancel = moveStop
            
            # footer
            btn_reboot = E('button').attr('id','camreboot').attr('class','btn btn-danger').inner_html('Herstarten')
            btn_reboot.element.onclick = reboot
            inp_publish = E('input').attr('type','checkbox').attr('name','streampublish').attr('value','1').attr('class','form-check-input')
            inp_publish.element.checked = await getStreamPublish()
            inp_publish.element.onchange = setStreamPublish
            inp_border = E('input').attr('type','checkbox').attr('class','form-check-input')
            inp_border.element.onchange = setBorder

            div_footer.append(
                E('div').attr('class','streampublish form-check').append( E('label').attr('class','form-check-label').append(
                    inp_publish,
                    E('span').inner_html(' Live uitzenden')
                ) ),
                E('div').attr('class','raster form-check').append( E('label').attr('class','form-check-label').append(
                    inp_border,
                    E('span').inner_html(' Raster tonen')
                ) ),
                E('div').attr('class','reboot').append( btn_reboot )
            )
            
            # set active cam obj
            cam = self.cameras[self.camid]

            # load presets
            presets = await utils.post(utils.get_url("camera/getPresets"), {'id':self.camid})

            if presets['err'] in 'connection':
                div_live_err.append(
                    E('div').attr('class','alert alert-danger').inner_html("Camera is niet beschikbaar.")
                )
            elif presets['err'] == 'fout':
                div_live_err.append(
                    E("div")
                    .attr("style", "color:red;")
                    .inner_html('Onverwachte fout.')
                )
            else:
                div_move.remove_attr('class')
                div_footer.remove_attr('class')

                if len(presets['presets']) == 0:
                    div_presets.append( E('p').inner_html("Geen presets") )
                else:
                    ul = E('ul')
                    for pr in presets['presets']:
                        btn = E('button').attr('name','p').attr('value',pr['token']).attr('class','btn btn-primary preset_'+pr['token']).inner_html(pr['token'])
                        btn.element.onclick = goto_preset
                        lbl = E('input').attr('type','text').attr('id',pr['token']).attr('value',pr['label']).attr('class','form-control')
                        lbl.element.onchange = setPresetLabel

                        ul.append( E('li').append( btn,lbl ) )

                    div_presets.append( ul )
                    await checkActivePreset()
            
                # load live
                uri = await utils.post(utils.get_url("camera/getLive"), {'id':self.camid})

                if uri['success']:
                    ws = f"ws://{cam.url_extern}:{cam.port_ws}"
                    video = E('video').attr('id','preview').attr('data-host',ws).attr('data-stream',uri['uri']).attr('autoplay','autoplay').attr('muted','muted').attr('playsinline','playsinline').attr('width','100%')
                    video.element.addEventListener(
                        "contextmenu",
                        lambda evt: evt.preventDefault()
                    )
                    div_live_video.remove_childs()
                    div_live_video.append(video)
                    
                    mediauri = ws+uri['uri']
                    __pragma__('js', '{}', '''
                        var wfs = new Wfs();
                        wfs.attachMedia(video.element, mediauri);
                    ''')
                else:
                    div_live_err.append(
                        E('p').inner_html(uri['error'])
                    )

        async def checkActivePreset():
            result = await utils.post(utils.get_url("camera/getActivePreset"), {'id':self.camid})

            for btn in div_presets.element.querySelectorAll("button"):
                btn.classList.remove("btn-success")
                btn.classList.add("btn-primary")

            div_presets.element.querySelector("button.preset_"+result).classList.add("btn-success")
            div_presets.element.querySelector("button.preset_"+result).classList.remove("btn_primary")

            setTimeout(checkActivePreset, 2000)

        async def goto_preset(evt):
            preset = int(evt.target.value)
            result = await utils.post(utils.get_url("camera/gotoPreset"), {'id':self.camid, 'preset':preset})
            
            if result['success']:
                for btn in div_presets.element.querySelectorAll("button"):
                    btn.classList.add("btn-primary")
                    btn.classList.remove("btn-success")

                evt.target.classList.remove("btn-primary")
                evt.target.classList.add("btn-success")

        async def setPresetLabel(evt):
            token = int(evt.currentTarget.id)
            label = str(evt.currentTarget.value)

            result = await utils.post(utils.get_url("camera/setPresetLabel"), {'id':self.camid, 'token':token, 'label':label})
            
        async def moveStart(evt):
            for btn in div_presets.element.querySelectorAll("button"):
                btn.classList.add("btn-primary")
                btn.classList.remove("btn-success")
                
            await utils.post(utils.get_url("camera/moveStart"),{"id": self.camid,"direction": evt.currentTarget.id})

        async def moveStop(evt):
            await utils.post(utils.get_url("camera/moveStop"),{"id": self.camid})
        
        async def moveClick(evt):
            await moveStart(evt)

            # kleine vertraging zodat de camera de opdracht zeker verwerkt
            await utils.sleep(0.075)

            await moveStop()

        async def getStreamPublish():
            result = await utils.post(utils.get_url("camera/getStreamPublish"),{"id": self.camid})
            return result["success"]

        async def setStreamPublish(evt):
            publish = evt.currentTarget.checked

            await utils.post(utils.get_url("camera/setStreamPublish"),{"id": self.camid, "publish": publish})

        async def reboot():
            if confirm("Camera herstarten?"):
                await utils.post(utils.get_url("camera/reboot"),{"id": self.camid})

        async def initialize():
            cameras = await utils.post(utils.get_url("camera/getCameras"), {})
            if cameras.success:
                self.cameras = cameras.cameras

                btn_cameras()
                btn_presets()

        def setBorder(evt):
            if evt.currentTarget.checked:
                div_live_hor.attr('style','display:block')
                div_live_ver.attr('style','display:block')
            else:
                div_live_hor.attr('style','display:none')
                div_live_ver.attr('style','display:none')

        self.refresh = initialize

    def show(self):
        main.remove_childs()
        main.append(self)
        self.refresh()

