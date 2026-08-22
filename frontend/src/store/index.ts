import Vue from 'vue'
import Vuex from 'vuex'
import { IAppState } from './modules/app'
import { IUserState } from './modules/user'
import { INotificationState } from './modules/notification'
import { IViewModeState } from './modules/viewMode'

Vue.use(Vuex)

export interface IRootState {
  app: IAppState
  user: IUserState
  notification: INotificationState
  viewMode: IViewModeState
}

// Declare empty store first, dynamically register all modules later.
export default new Vuex.Store<IRootState>({})
