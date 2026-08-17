$(function() {
	var $camid = null;
	var $cameras = null;
	var $wfs = new Wfs();

	getLogin();

	/*
	* get login
	*/
	function getLogin(){
		$('#login, #cams, #presets, #live, #move, #footer, #user').hide();

		$.ajax({
			url: "/login/login",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			success: function($response){
				if( $response.success ){
					$('#cams, #live, #user').show();

					setUsername( $response.username );

					getCameras();
				} else {
					$('#login').show();

					$('#login button').click( function(){
						$.ajax({
							url: "/login/login",
							type: "POST",
							contentType: "application/json",
							dataType: 'json',
							data: JSON.stringify({
								username: $('#login #current-username').val(),
								password: $('#login #current-password').val()
							}),
							success: function($response){
								if( $response.success ){
									$('#login').hide();
									$('#cams, #user').show();
									
									setUsername( $('#login #current-username').val() );
									
									getCameras();
								} else {
									$('#login .fout').show();
								}
							}
						});
					});
				}
			}
		});
	}

	function setUsername(username){
		$('#user .username').text(username)
		$('#user #current-username').val(username)
	}

	/*
	* get cams
	*/
	function getCameras(){
		$('#login, #presets, #live video, #move, #footer').hide();

		$.ajax({
			url: "/camera/getCameras",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			success: function($response){
				if( $response.success ){
					$('#cams').show();
					$('#cams ul').empty();
					$cameras = $response.cameras;

					$index = 0;
					for(let $item of $cameras){
						$('#cams ul').append('<li><button value="'+$index+'"'+($index==0?" class='active'":"")+'>'+$item.name+'</button></li>');
						$index++;
					}

					$('#cams button').on('click', function(){
						getPresets($(this));
					});

					// next step: load presets
					getPresets( $('#cams li:first-child button') );
				} else {
					$('#live .alert').text($response.error).show();  // niet ingelogd
				}
			}
		});
	}

	/*
	* handle cams
	*/
	function getPresets( $btn ){
		$('#login, #presets, #live video, #move, #footer').hide();

		$camid = $btn.val();
		$toggleLabels = $('.toggleLabels').is(':checked');

		$('#cams button').removeClass('active');
		$btn.addClass('active');
		
		// restart wfs
		$wfs.destroy();
		$wfs = null;
		$wfs = new Wfs();

		$.ajax({
			url: "/camera/getPresets",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
			}),
			success: function($response){ 
				if( $response.err == 'connection' ){
					$('#live .alert').text("Camera is niet beschikbaar.").show();
				} else {
					// clear preset buttons
					$('#presets ul').empty();

					// add preset buttons to dom
					for(let $item of $response.presets){
						$('#presets ul').append('<li'+($toggleLabels?'':' class="basic"')+'><button value="'+$item.token+'" class="preset_'+$item.token+'">'+$item.token+'</button><span class="label"> '+$item.label+'</span></li>');
					}
					$('#move, #presets, #footer').show();
					
					checkActivePreset();

					// add preset click event
					$('#presets button').click(function( $e ){
						gotoPreset( $(this) );
					});

					// load livestream
					getLive();

					// get streampublish parameter
					getStreamPublish();

					// set Instellingen link
					$('#footer .caminstellingen').attr('href','http://'+$cameras[$camid].url_extern)
				}
			}
		});
	}

	function checkActivePreset(){
		$.ajax({
			url: "/camera/getActivePreset",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
			}),
			success: function($response){ 
				$('#presets ul button').removeClass('active');
				$('#presets ul button.preset_'+$response).addClass('active')

				setTimeout(checkActivePreset, 2000);
			}
		});
	}

	/*
	 * getLive
	 */
	function getLive(){
		$('#live video').hide();

		$.ajax({
			url: "/camera/getLive",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
			}),
			success: function($response){ 
				if( $response.success ){ 
					if( $response.uri !== false ){
						var $video = document.getElementById("preview"); // niet als jQuery object laden!
						if( $video !== null ){
							$video.addEventListener('contextmenu', function ($e) { 
								$e.preventDefault(); 
							});

							$wfs.attachMedia( $video, "ws://"+$cameras[$camid].url_extern+":"+$cameras[$camid].port_ws+$response.uri );
						}
						$('#live video').show();
						$('#live .alert').hide();
					} else {
						//$('#live .alert').text($response.error).show();
						$('#live .alert').text("Video is niet beschikbaar.").show();
					}
				} else {
					//console.error('getLive fail: '+$response.error);
					$('#live .alert').text("Video is niet beschikbaar.").show();
				}
			}
		});
	}

	/*
	 * restore preset label setting from cookie
	 */
	let $cookie_raw = document.cookie.split("; ");
	var $cookie = [];
	for( $c in $cookie_raw){
		let $line = $cookie_raw[$c].split("=");
		$cookie[$line[0]] = $line[1];
	}

	if( 'camera_app_labels' in $cookie ){
		if( $cookie.camera_app_labels == 'true' ){
			$('.toggleLabels').attr('checked',true);
			$('#presets ul li').removeClass('basic');
		}
	}
	if( 'camera_app_audio' in $cookie ){
		$('.toggleAudio').attr('checked', ($cookie.camera_app_audio == 'true') );
		toggleAudio();
	}

	/*
	 * toggle preset labels
	 */
	$('.toggleLabels').click(function(){
		if( $(this).is(':checked') ){
			$('#presets ul li').removeClass('basic');
			document.cookie = "camera_app_labels=true;max-age=2628000"; //max-age = 1 month
		} else {
			$('#presets ul li').addClass('basic');
			document.cookie = "camera_app_labels=false;max-age=2628000"; //max-age = 1 month
		}
	});

	/*
	 * handle preset
	 */
	function gotoPreset( $btn ){
		$('#presets button').removeClass('active');
		$btn.addClass('active');
		
		$.ajax({
			url: "/camera/gotoPreset",
			type: "POST",
			contentType: "application/json",
			data: JSON.stringify({
				id: parseInt($camid),
				preset: parseInt($btn.val())
			})
		});
	}

	/*
	 * StreamPublish
	 */
	function getStreamPublish(){
		$.ajax({
			url: "/camera/getStreamPublish",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
			}),
			success: function($response){
				$('#footer .streampublish input').attr('checked', $response.success)
			}
		});
	}
	$('#footer .streampublish input').click(function( $e ){
		var $btn = $(this);
		if( $btn.is(":checked") ){
			$val = 1;
		} else if( confirm("Live uitzending uitschakelen?") ) {
			$val = 0;
		} else {
			return false;
		}

		$.ajax({
			url: "/camera/setStreamPublish",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
				publish: $val,
			})
		});
	});

	/*
	 * toggleAudio
	 */
	$('.toggleAudio').click(function(){
		toggleAudio();
	});

	function toggleAudio(){
		$video = document.getElementById("preview");
		if( $('.toggleAudio').is(':checked') ){
			$video.muted = false;
			$('#preview').removeAttr("muted");
			document.cookie = "camera_app_audio=true;max-age=2628000"; //max-age = 1 month
		} else {
			$video.muted = true;
			$('#preview').attr("muted", "");
			document.cookie = "camera_app_audio=false;max-age=2628000"; //max-age = 1 month
		}
	}

	/*
	 * reboot
	 */
	$('#camreboot').click(function( $e ){
		if( confirm("Camera herstarten?") ) {
			var $btn = $(this);
			$.ajax({
				url: "/camera/reboot",
				type: "POST",
				contentType: "application/json",
				dataType: 'json',
				data: JSON.stringify({
					id: parseInt($camid),
				})
			});
		}
	});
	
	/*
	 * move
	 */
	$('#move button.ptzmove').on('click touchstart mousedown', function($evt){
		console.log($evt.type)
		if( $evt.type == 'click' ){
			moveClick($evt);
		} else {
			moveStart($evt);
		}
	});
	$('#move button.ptzstop').on('click touchstart mousedown', function($evt){
		console.log($evt.type)
		moveStop();
	});
	$('#move button.ptzmove').on('touchend mouseup', function($evt){
		moveStop();
	});
	function moveStart($evt){
		$('#presets button').removeClass('active');
		$.ajax({
			url: "/camera/moveStart",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
				direction: $evt.currentTarget.id
			})
		});
	}
	function moveStop(){
		$('#presets button').removeClass('active');
		$.ajax({
			url: "/camera/moveStop",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				id: parseInt($camid),
			})
		});
	}
	function moveClick($evt){
		moveStart($evt);
		stop = setTimeout(moveStop, 75);
	}

	/*
	 * user management
	 */
	$('#user .change').click( function(){
		$('#user .buttons').hide();
		$('#user .form').show();
	});

	$('#user .buttons .logout').click( function(){
		$.ajax({
			url: "/login/logout",
			type: "POST",
			success: function(){
				window.location.reload();
			}
		});
	});

	$('#user .form button').click( function(){
		$.ajax({
			url: "/login/setUser",
			type: "POST",
			contentType: "application/json",
			dataType: 'json',
			data: JSON.stringify({
				username: $('#user .form #current-username').val(),
				password: $('#user .form #current-password').val()
			}),
			success: function($response){
				if( $response.success ){
					$('#user .form').hide();
					$('#user .buttons').show();
				} else {
					//alert($response.error);
					alert("Gegevens niet opgeslagen.");
				}
			}
		});
	});
});