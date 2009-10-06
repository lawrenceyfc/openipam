import types

import cherrypy

import framework
import re
from basepage import BasePage
from resource.submenu import submenu, OptionsSubmenu
from openipam.utilities import misc, error, validation
from openipam.utilities.perms import Perms
from openipam.web.resource.utils import redirect_to_referer
from openipam.config import frontend

class Hosts(BasePage):
	'''The hosts class. This includes all pages that are /hosts/*'''

	def __init__(self):
		BasePage.__init__(self)
		
		# Object for wrapping HTML into the template
		self.__template = framework.Basics("hosts", javascript=("/scripts/jquery/ui/jquery-ui-personalized.min.js", "/scripts/hosts.js"))
		
	def leftnav_actions(self, current=None):
		'''
		Returns the html for the leftnav
		@param current: a string of the current action that will be highlighted
		'''
		
		actions = ('Add Host',)
		action_links = ('/hosts/add',)
		
		return submenu(values=actions, links=action_links, title="Actions", selected=current)
	
	def leftnav_options(self):
		'''
		Returns the html for the leftnav options on the Manage Hosts tab
		'''
		
		options = (('Show expired hosts','Hide expired hosts',), ('Show everyone\'s hosts','Show only my hosts',),)
		options_links = ('/hosts/?show_expired', '/hosts/?show_all')
		selected = (cherrypy.session['show_expired_hosts'], cherrypy.session['show_all_hosts'])
		
		return OptionsSubmenu(values=options, links=options_links, title="Options", selected=selected)
	
	def get_leftnav(self, action="", show_options=True):
		return '%s%s' % (self.leftnav_actions(action), (self.leftnav_options() if show_options else ''))
	
	def get_hosts(self, page=0, ip=None, mac=None, hostname=None, namesearch=None, network=None, username=None, expiring=False, count=False, order_by='hostname'):
		"""
		@param page: the current page the user is viewing
		@param show_all_hosts: default false, will only show hosts that the current user has OWNER over
		"""
			
		limit = cherrypy.session['hosts_limit']
		
		# This would be better as an argument
		additional_perms = str(frontend.perms.OWNER)
		if cherrypy.session['show_all_hosts']:
			additional_perms = '00000000'

		if hostname:
			hostname = hostname.replace('*','%')
		
		if namesearch:
			namesearch = namesearch.replace('*','%')
		
		values = {
			'additional_perms' : str(additional_perms),
			'limit' : limit,
			'page' : int(page),
			'show_expired' : cherrypy.session['show_expired_hosts'],
			'ip' : ip,
			'mac' : mac,
			'count' : count,
			'username' : username,
			'hostname' : hostname,
			'namesearch' : namesearch,
			'order_by' : order_by,
			'network' : network,
			'expiring' : expiring
			}
		
		num_hosts = -1
		try:
			hosts = self.webservice.get_hosts( values )
			if count:
				num_hosts = hosts[0]
				hosts=hosts[1]
		except Exception, e:
			if error.parse_webservice_fault(e) == "NotUser":
				hosts = []
			else:
				raise
		
		for host in hosts:
			host['clean_mac'] = misc.fix_mac(host['mac'])
			host['description'] = host['description'].encode('utf8') if host['description'] else ''
			
		# Get permissions for those MAC addresses
		perms = self.webservice.find_permissions_for_hosts( { 'hosts' : hosts } )
		perms = perms[0] if perms else perms
		
		for host in hosts:
			if perms.has_key(host['mac']):
				host['has_permissions'] = ((Perms(perms[host['mac']]) & frontend.perms.OWNER) == frontend.perms.OWNER)
			else:
				host['has_permissions'] = '00000000'
		
		if count:
			return num_hosts,hosts
		return hosts
		
	def mod_host_attributes(self, values=None):
		"""
		Return the attributes passed to the Add/Edit host template that are shared between
		Add and Edit functionality
		"""
		
		if not values:
			values = {}
		
		# FIXME: this needs to come from the backend
		values['allow_dynamic_ip'] = frontend.allow_dynamic_ip

		values['networks'] = self.webservice.get_networks( { 'additional_perms' : str(frontend.perms.ADD), 'order_by' : 'network' } )
		values['domains'] = self.webservice.get_domains( { 'additional_perms' : str(frontend.perms.ADD), 'show_reverse' : False, 'order_by' : 'name' } )
		values['expirations'] = self.webservice.get_expiration_types()
 		values['groups'] = self.webservice.get_groups( { 'ignore_usergroups' : True, 'order_by' : 'name' } )
		
		return values

	def add_host(self, **kw):
		'''
		Process the add_host request
		'''
		
		# Confirm user authentication
		self.check_session()
		
		mac = self.webservice.register_host(
			{
			'mac' : kw['mac'],
			'hostname' : kw['hostname'],
			'domain' : int(kw['domain']) if kw['domain'] else None,
			'description' : kw['description'],
			'expiration' : int(kw['expiration']),
			'is_dynamic' : kw.has_key('dynamicIP'),
			'owners_list' : kw['owners_list'], 
			'network' : (kw['network'] if kw.has_key('network') and kw['network'] else None),
			'add_host_to_my_group' : False,
			'address' : (kw['ip'] if kw.has_key('ip') else None)
			})
		
		raise cherrypy.HTTPRedirect('/hosts/search/?q=%s' % misc.fix_mac(mac))
	
	def edit_host(self, **kw):
		'''
		Process the edit_host request
		'''
		
		# Confirm user authentication
		self.check_session()
		
		self.webservice.change_registration(
			{
			'old_mac' : kw['old_mac'],
			'mac' : kw['mac'],
			'hostname' : (kw['hostname'] if kw.has_key('hostname') else None),
			'domain' : (int(kw['domain']) if kw.has_key('domain') else None),
			'description' : kw['description'],
			'expiration' : (int(kw['expiration']) if kw.has_key('did_renew_host') else None),
			'is_dynamic' : kw.has_key('dynamicIP'),
			'owners_list' : kw['owners_list'], 
			'network' : (kw['network'] if kw.has_key('did_change_ip') or (kw.has_key('was_dynamic') and not kw.has_key('dynamicIP')) else None),
			'address' : (kw['ip'] if kw.has_key('did_change_ip') and kw.has_key('ip') else None)
			})
		
		raise cherrypy.HTTPRedirect('/hosts/search/?q=%s' % misc.fix_mac(kw['mac'] if kw['mac'] else kw['old_mac']))

	#-----------------------------------------------------------------
	
	@cherrypy.expose
	def index(self, page=0, **kw):
		"""
		The main hosts page
		"""
		
		# Confirm user authentication
		self.check_session()
		
		# Initialization
		values = {}
		
		# Toggle 'Show expired hosts' and 'Show all hosts'
		if kw.has_key('show_expired'):
			cherrypy.session['show_expired_hosts'] = not cherrypy.session['show_expired_hosts']
			redirect_to_referer()
		if kw.has_key('show_all'):
			cherrypy.session['show_all_hosts'] = not cherrypy.session['show_all_hosts']
			redirect_to_referer()
			
		if cherrypy.session['has_global_owner']:
			values['show_search_here'] = True
		else:
			#values['num_hosts'],values['hosts'] = self.get_hosts( page=page, count=True )
			raise cherrypy.HTTPRedirect('/hosts/search/?q=user%%3a%s' % cherrypy.session['username'])
			
		values['show_all_hosts'] = cherrypy.session['show_all_hosts']

		values['url'] = cherrypy.url()

		return self.__template.wrap(leftcontent=self.get_leftnav(), filename='%s/templates/hosts.tmpl'% frontend.static_dir, values=values)
	
	@cherrypy.expose
	def add(self, **kw):
		"""
		The Add Host page
		"""
		
		# Confirm user authentication
		self.check_session()
		
		if kw.has_key('submit'):
			try:
				self.add_host(**kw)
			except Exception, e:
				if error.parse_webservice_fault(e) == "ListXMLRPCFault":
					e.faultString = e.faultString.replace('[ListXMLRPCFault]', '')
					e.message = e.faultString.split(';')
				else:
					raise
				values = self.mod_host_attributes({ 'submitted_info' : kw })
				values['message'] = error.get_nice_error(e)
		else:		
			values = self.mod_host_attributes()
			
		return self.__template.wrap(leftcontent=self.get_leftnav(action="Add Host", show_options=False), filename='%s/templates/mod_host.tmpl'%frontend.static_dir, values=values)
	
	@cherrypy.expose
	def edit(self, macaddr=None, **kw):
		"""
		The Add Host page
		"""
		
		# Confirm user authentication
		self.check_session()
		
		if not macaddr:
			raise cherrypy.HTTPRedirect('/hosts')
		
		values = {}
		
		if kw.has_key('submit'):
			try:
				self.edit_host(**kw)
			except Exception, e:
				if error.parse_webservice_fault(e) == "ListXMLRPCFault":
					e.faultString = e.faultString.replace('[ListXMLRPCFault]', '')
					e.message = e.faultString.split(';')
				else:
					raise
				values['message'] = error.get_nice_error(e)
				
		# Initialization
		values = self.mod_host_attributes( values )
		
		host = self.webservice.get_hosts( { 'mac' : macaddr, 'additional_perms' : str(frontend.perms.MODIFY) } )
		if not host:
			raise cherrypy.HTTPRedirect('/denied')
		host = host[0]

		owners = self.webservice.find_owners_of_host( { 'mac' : macaddr } )
		is_dynamic = self.webservice.is_dynamic_host( { 'mac' : macaddr } )
		domain = self.webservice.get_domains( { 'contains' : str(host['hostname']), 'additional_perms' : str(frontend.perms.ADD) } )
		ips = self.webservice.get_dns_records( { 'mac' : macaddr, 'tid': 1 } )

		values['has_domain_access'] = bool(domain)
		if domain:
			values['domain'] = kw['domain'] if kw.has_key('domain') else domain[0]['id']
			
		values['ips'] = ips
		values['host'] = host
		values['host']['description'] = values['host']['description'].encode('utf8') if values['host']['description'] else ''
		values['owners'] = owners
		values['is_dynamic'] = is_dynamic
		
		return self.__template.wrap(leftcontent=self.get_leftnav(show_options=False), filename='%s/templates/mod_host.tmpl'%frontend.static_dir, values=values)
	
	@cherrypy.expose
	def search(self, q='', expiring=False, page=0, order_by='hostname', success=False, **kw):
		'''
		The search page where the search form POSTs
		'''
		
		# Confirm user authentication
		self.check_session()
		limit = cherrypy.session['hosts_limit']
		# Initialization
		values = {}
		page = int(page)

		if re.search(r'[^a-zA-Z.,_ ]',order_by):
			raise Exception('Who do you think you are?')
		
		if not q and not kw.keys():
			if not expiring:
				raise cherrypy.InternalRedirect('/hosts')
			else:
				q = "user:%s" % cherrypy.session['username']

		if success:
			values['global_success'] = 'Hosts Updated Successfully'
		
		if expiring:
			kw['expiring'] = expiring
		if page:
			kw['page'] = page

		special_search = {
				'ip':'ip', 'mac':'mac', 'user':'username',
				'username':'username', 'net':'network',
				'network':'network', 'hostname':'namesearch',
				'name':'namesearch',
				}

		for element in q.split( ):
			if validation.is_mac(element):
				kw['mac'] = element
			elif validation.is_ip(element):
				kw['ip'] = element
			elif validation.is_cidr(element):
				kw['network'] = element
			elif ':' in element:
				# I strongly recommend that we do this next to last...
				stype,value = element.split(':',1)
				if special_search.has_key(stype):
					kw[special_search[stype]] = value
				else:
					raise error.InvalidArgument('Unrecognized special search type: %s (value: %s)' % (stype, value))
			else:
				# Let's assume it's a hostname.
				if '.' in element or '*' in element or '%' in element:
					namesearch = element.replace('%','*')
				else:
					namesearch = '*%s*' % element.replace('%','*')
				if kw.has_key('namesearch'):
					raise error.InvalidArgument('Invalid search string -- more than one name (%s, %s)' % (kw['namesearch'], namesearch))
				kw['namesearch'] = namesearch


		# FIXME: this might break with special characters
		# FIXME: need more thorough input validation
		kw_elements = []
		kw_keys = kw.keys()
		kw_keys.sort()
		for k in kw_keys:
			v = kw[k]
			if hasattr(v, '__contains__') and '&' in v:
				raise error.InvalidArgument('& is not valid here')
			if k != 'page':
				kw_elements.append('%s=%s' % (k,v))

		search_str = '/search/?%s&' % '&'.join(kw_elements)
		print search_str

		if q:
			# we are ignoring order_by here, but this should only happen with a new search anyway...
			raise cherrypy.HTTPRedirect('/hosts%s' % ( search_str[:-1] ) )

		kw['order_by'] = order_by

		values['search'] = search_str
		values['page'] = int(page)
		values['show_all_hosts'] = cherrypy.session['show_all_hosts']

		values['num_hosts'],values['hosts'] = self.get_hosts( count=True, **kw )
		values['len_hosts'] = len(values['hosts'])
		values['num_pages'] = int( (values['num_hosts'] + limit - 1) / limit )
		values['first_host'] = page * limit + 1
		values['last_host'] = page * limit + len(values['hosts'])
		values['limit'] = limit

		values['username'] = cherrypy.session['username']
		values['order_by'] = order_by
		
		values['url'] = cherrypy.url()

		return self.__template.wrap(leftcontent=self.get_leftnav(), filename='%s/templates/hosts.tmpl'%frontend.static_dir, values=values)
	
	
	@cherrypy.expose
	def multiaction(self, multiaction=None, multihosts=None, multiurl=None, **kw):
		"""
		Perform an action on a list of hosts.
		"""
		
		# Confirm user authentication
		self.check_session()

		ref = cherrypy.request.headers['Referer']
		
		if not multihosts:
			raise error.InvalidArgument('No hosts selected!')

		if type(multihosts) != types.ListType:
			multihosts = [multihosts]

		if multiaction == 'delete':
			self.webservice.delete_hosts( {'hosts':multihosts} );
		elif multiaction == 'renew':
			self.webservice.renew_hosts( {'hosts':multihosts} );
		# need to get the owners...
		#elif multiaction == 'owners':
		#	self.webservice._hosts( hosts=multihosts )
		else:
			raise cherrypy.HTTPRedirect(ref)

		# FIXME: We should have the calling page include its URL in the form
		# Gahh....evill....re-write me....
		
		sep = "&" if "?" in ref else "?"
		success = "%ssuccess=True" % sep if "success" not in ref else ""
		ref = "%s%s" % (ref, success)

		raise cherrypy.HTTPRedirect(ref)
	
	
	
	

